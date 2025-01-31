use std::{pin::Pin, sync::{Arc}, ops::DerefMut};

use futures::{channel::oneshot, stream, StreamExt};
use tokio::{net::{tcp::{OwnedWriteHalf, OwnedReadHalf}, TcpListener}, task::JoinHandle, io::{AsyncWrite, copy}, process::{ChildStdout, ChildStdin, Child}, sync::Mutex};
use tokio_util::io::{ReaderStream, StreamReader};

use proto_flow::capture::PullResponse;
use proto_flow::flow::DriverCheckpoint;

use crate::{apis::{InterceptorStream, FlowCaptureOperation, StreamMode}, interceptors::airbyte_source_interceptor::AirbyteSourceInterceptor, errors::{Error, io_stream_to_interceptor_stream, interceptor_stream_to_io_stream}, libs::{command::{invoke_connector_delayed, check_exit_status}, protobuf::{decode_message, encode_message}}};

async fn flatten_join_handle<T, E: std::convert::From<tokio::task::JoinError>>(
    handle: JoinHandle<Result<T, E>>,
) -> Result<T, E> {
    match handle.await {
        Ok(Ok(result)) => Ok(result),
        Ok(Err(err)) => Err(err),
        Err(err) => Err(err.into()),
    }
}

async fn flow_socket(socket_path: &str, mode: &StreamMode) -> Result<(OwnedReadHalf, OwnedWriteHalf), Error> {
    match mode {
        StreamMode::TCP => {
            let listener = TcpListener::bind(socket_path).await?;
            let (stream, _) = listener.accept().await?;
            let (read_half, write_half) = stream.into_split();
            Ok((read_half, write_half))
        }
    }
}

async fn flow_read_stream(read_half: OwnedReadHalf) -> Result<InterceptorStream, Error> {
    Ok(Box::pin(io_stream_to_interceptor_stream(ReaderStream::new(read_half))))
}

fn flow_write_stream(write_half: OwnedWriteHalf) -> Arc<Mutex<Pin<Box<dyn AsyncWrite + Send + Sync>>>> {
    Arc::new(Mutex::new(Box::pin(write_half)))
}

fn airbyte_response_stream(child_stdout: ChildStdout) -> InterceptorStream {
    Box::pin(io_stream_to_interceptor_stream(ReaderStream::new(child_stdout)))
}

pub fn parse_child(mut child: Child) -> Result<(Child, ChildStdin, ChildStdout), Error> {
    let stdout = child.stdout.take().ok_or(Error::MissingIOPipe)?;
    let stdin = child.stdin.take().ok_or(Error::MissingIOPipe)?;

    Ok((child, stdin, stdout))
}

pub async fn run_airbyte_source_connector(
    entrypoint: String,
    op: FlowCaptureOperation,
    socket_path: &str,
    stream_mode: StreamMode,
) -> Result<(), Error> {
    let mut airbyte_interceptor = AirbyteSourceInterceptor::new();

    let args = airbyte_interceptor.adapt_command_args(&op);
    let full_entrypoint = format!("{} \"{}\"", entrypoint, args.join("\" \""));

    let (mut child, child_stdin, child_stdout) =
        parse_child(invoke_connector_delayed(full_entrypoint)?)?;

    let (read_half, write_half) = flow_socket(socket_path, &stream_mode).await?;

    // std::thread::sleep(std::time::Duration::from_secs(400));
    let adapted_request_stream = airbyte_interceptor.adapt_request_stream(
        &op,
        flow_read_stream(read_half).await?
    )?;

    let adapted_response_stream =
        airbyte_interceptor.adapt_response_stream(&op, airbyte_response_stream(child_stdout))?;

    // Keep track of whether we did send a Driver Checkpoint as the final message of the response stream
    // See the comment of the block below for why this is necessary
    let (tp_sender, tp_receiver) = oneshot::channel::<bool>();
    let adapted_response_stream = if op == FlowCaptureOperation::Pull {
        Box::pin(stream::try_unfold(
            (false, adapted_response_stream, tp_sender),
            |(transaction_pending, mut stream, sender)| async move {
                let (message, raw) = match stream.next().await {
                    Some(bytes) => {
                        let bytes = bytes?;
                        let mut buf = &bytes[..];
                        // This is infallible because we must encode a PullResponse in response to
                        // a PullRequest. See airbyte_source_interceptor.adapt_pull_response_stream
                        let msg = decode_message::<PullResponse, _>(&mut buf)
                            .await
                            .unwrap()
                            .unwrap();
                        (msg, bytes)
                    }
                    None => {
                        sender.send(transaction_pending).map_err(|_| Error::AirbyteCheckpointPending)?;
                        return Ok(None);
                    }
                };

                Ok(Some((raw, (!message.checkpoint.is_some(), stream, sender))))
            },
        ))
    } else {
        adapted_response_stream
    };

    let response_write = flow_write_stream(write_half);

    let streaming_all_task = tokio::spawn(streaming_all(
        adapted_request_stream,
        child_stdin,
        Box::pin(adapted_response_stream),
        response_write.clone(),
    ));

    let cloned_op = op.clone();
    let exit_status_task = tokio::spawn(async move {
        let exit_status_result = check_exit_status("airbyte source connector:", child.wait().await);

        // There are some Airbyte connectors that write records, and exit successfully, without ever writing
        // a state (checkpoint). In those cases, we want to provide a default empty checkpoint. It's important that
        // this only happens if the connector exit successfully, otherwise we risk double-writing data.
        if exit_status_result.is_ok() && cloned_op == FlowCaptureOperation::Pull {
            tracing::debug!("airbyte-to-flow: waiting for tp_receiver");
            // the received value (transaction_pending) is true if the connector writes output messages and exits _without_ writing
            // a final state checkpoint.
            if tp_receiver.await.unwrap() {
                // We generate a synthetic commit now, and the empty checkpoint means the assumed behavior
                // of the next invocation will be "full refresh".
                tracing::warn!("go.estuary.dev/W001: connector exited without writing a final state checkpoint, writing an empty object {{}} merge patch driver checkpoint.");
                let mut resp = PullResponse::default();
                resp.checkpoint = Some(DriverCheckpoint {
                    driver_checkpoint_json: b"{}".to_vec(),
                    rfc7396_merge_patch: true,
                });
                let encoded_response = &encode_message(&resp)?;
                let mut buf = &encoded_response[..];
                let mut writer = response_write.lock().await;
                copy(&mut buf, writer.deref_mut()).await?;
            }
        }

        if exit_status_result.is_ok() {
            // We wait a few seconds to let any remaining writes to be done
            // since the select below will not wait for `streaming_all` task to finish
            // once exit_status has been received.
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
        }

        exit_status_result
    });

    // If streaming_all_task errors out, we error out and don't wait for exit_status, on the other
    // hand once the connector has exit (exit_status_task completes), we don't wait for streaming
    // task anymore
    tokio::select! {
        Err(e) = flatten_join_handle(streaming_all_task) => Err(e),
        resp = flatten_join_handle(exit_status_task) => resp,
    }?;

    tracing::debug!("airbyte-to-flow: connector_runner done");
    Ok(())
}

/// Stream request_stream into request_stream_writer and response_stream into
/// response_stream_writer.
async fn streaming_all(
    request_stream: InterceptorStream,
    mut request_stream_writer: ChildStdin,
    response_stream: InterceptorStream,
    response_stream_writer: Arc<Mutex<Pin<Box<dyn AsyncWrite + Sync + Send>>>>,
) -> Result<(), Error> {
    let mut request_stream_reader = StreamReader::new(interceptor_stream_to_io_stream(request_stream));
    let mut response_stream_reader = StreamReader::new(interceptor_stream_to_io_stream(response_stream));

    let request_stream_copy =
        tokio::spawn(
            async move {
                copy(&mut request_stream_reader, &mut request_stream_writer).await?;
                tracing::debug!("airbyte-to-flow: request_stream_copy done");
                Ok::<(), std::io::Error>(())
            },
        );

    let response_stream_copy = tokio::spawn(async move {
        let mut writer = response_stream_writer.lock().await;
        copy(&mut response_stream_reader, writer.deref_mut()).await?;
        tracing::debug!("airbyte-to-flow: response_stream_copy done");
        Ok(())
    });

    tokio::try_join!(
        flatten_join_handle(request_stream_copy),
        flatten_join_handle(response_stream_copy)
    )?;

    tracing::debug!("airbyte-to-flow: streaming_all finished");
    Ok(())
}
