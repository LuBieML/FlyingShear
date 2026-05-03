import Trio_UnifiedApi as TUA
from typing import Optional, Callable
import logging
import threading
import time

class TrioConnection:
    def __init__(self, status_callback: Callable):
        self.status_callback = status_callback
        self.connection: Optional[TUA.TrioConnection] = None
        self._is_open: bool = False
        self._shutting_down: bool = False
        self._ip_address: Optional[str] = None
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._disconnect_cooldown_end = 0.0
        self._disconnect_cooldown_seconds = 1.0
        self._state_lock = threading.Lock()
        self._on_connection_lost: Optional[Callable] = None

        self._max_connection_attempts = 3
        self._connection_timeout_seconds = [5, 10, 15]

        logging.info("TrioConnection initialized")

    def _watchdog_loop(self):
        while not self._watchdog_stop.wait(0.5):
            if not (self.connection and self._is_open):
                continue
            try:
                heartbeat_done = threading.Event()
                heartbeat_error = []

                def _heartbeat():
                    try:
                        self.connection.SetVrValue(66, 1)
                    except Exception as e:
                        heartbeat_error.append(e)
                    finally:
                        heartbeat_done.set()

                t = threading.Thread(target=_heartbeat, name="WatchdogHeartbeat", daemon=True)
                t.start()
                if not heartbeat_done.wait(timeout=5.0):
                    self.mark_connection_lost()
                    logging.warning("Watchdog heartbeat timed out after 5s — connection lost")
                    break
                if heartbeat_error:
                    raise heartbeat_error[0]
            except Exception as exc:
                if 'Disconnected' in str(exc) or 'No connection' in str(exc):
                    self.mark_connection_lost()
                    logging.warning(f"Watchdog detected connection loss: {exc}")
                    break
                logging.debug(f"Watchdog failed to set VR(66): {exc}")

    def _cleanup_connection_async(self):
        conn = self.connection
        self.connection = None
        if conn is None:
            return
        def _close():
            try:
                conn.CloseConnection()
            except Exception:
                pass
        threading.Thread(target=_close, name="TrioCloseCleanup", daemon=True).start()

    def _start_watchdog(self):
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="TrioWatchdog", daemon=True)
        self._watchdog_thread.start()
        logging.debug("Watchdog thread started")

    def _stop_watchdog(self):
        if not self._watchdog_thread:
            return
        self._watchdog_stop.set()
        self._watchdog_thread.join(timeout=1.0)
        if self._watchdog_thread.is_alive():
            logging.warning("Watchdog thread did not terminate within timeout")
        self._watchdog_thread = None
        self._watchdog_stop = threading.Event()
        logging.debug("Watchdog thread stopped")

    def _get_disconnect_cooldown_remaining(self) -> float:
        now = time.monotonic()
        with self._state_lock:
            cooldown_end = self._disconnect_cooldown_end
        return max(0.0, cooldown_end - now)

    def _enter_disconnect_cooldown(self) -> None:
        with self._state_lock:
            self._disconnect_cooldown_end = time.monotonic() + self._disconnect_cooldown_seconds
        logging.debug(f"Disconnect cooldown active for {self._disconnect_cooldown_seconds:.2f}s")

    def get_disconnect_cooldown_remaining(self) -> float:
        return self._get_disconnect_cooldown_remaining()

    def is_disconnect_cooldown_active(self) -> bool:
        return self.get_disconnect_cooldown_remaining() > 0.0

    def event_handler(self, et, ival, sval):
        ival_repr = hex(ival) if isinstance(ival, int) else ival
        if not self.connection or not self._is_open or self._shutting_down:
            logging.debug(f"Ignoring event after connection closed/shutdown: {et}, {ival_repr}, {sval}")
            return

        if et == TUA.EventType.Error or et == TUA.EventType.Warning:
            logging.error(f"Event Handler - Error/Warning: ({ival_repr}) {sval}")
            try:
                if self.connection and self._is_open:
                    self.status_callback(f"Error: ({ival_repr}) {sval}", "error")
            except Exception as e:
                logging.warning(f"Failed to call status callback for error event: {e}")
        elif et == TUA.EventType.Message:
            logging.info(f"Event Handler - Message: {sval}")
            try:
                if self.connection and self._is_open:
                    self.status_callback(sval, "message")
            except Exception as e:
                logging.warning(f"Failed to call status callback for message event: {e}")

    def create_connection(self, mc_ip='192.168.1.250'):
        logging.info(f"Creating connection to {mc_ip}")
        if mc_ip == "PCMCAT":
            return TUA.TrioConnectionPCMCAT(self.event_handler)
        elif mc_ip == "FLEX7":
            return TUA.TrioConnectionFlex7(self.event_handler)
        else:
            connection = TUA.TrioConnectionTCP(self.event_handler, mc_ip)
            print(f"Created TCP connection object: {connection}")
            return connection

    _CANCELLED = "cancelled"

    def _attempt_connection_with_timeout(self, mc_ip: str, timeout_seconds: float,
                                         cancel_check: Optional[Callable] = None):
        connection_opened = threading.Event()
        connection_error = []

        def open_connection_thread():
            try:
                self.connection.OpenConnection()
                connection_opened.set()
            except Exception as e:
                connection_error.append(e)
                connection_opened.set()

        thread = threading.Thread(target=open_connection_thread, name="TrioConnectionThread", daemon=True)
        thread.start()

        elapsed = 0.0
        poll_interval = 0.5
        while elapsed < timeout_seconds:
            remaining = min(poll_interval, timeout_seconds - elapsed)
            if connection_opened.wait(timeout=remaining):
                if connection_error:
                    raise connection_error[0]
                return True
            elapsed += remaining
            if cancel_check and cancel_check():
                logging.info("Connection attempt cancelled by user during OpenConnection wait")
                return self._CANCELLED

        logging.warning(f"Connection attempt timed out after {timeout_seconds}s")
        return False

    def connect(self, mc_ip='192.168.1.250', progress_callback: Optional[Callable] = None,
                cancel_check: Optional[Callable] = None):
        if self.connection is not None and self._is_open:
            logging.info("Already connected.")
            return True

        remaining_cooldown = self._get_disconnect_cooldown_remaining()
        if remaining_cooldown > 0:
            logging.info(f"Connect attempt blocked during disconnect cooldown ({remaining_cooldown:.2f}s remaining).")
            self.status_callback("Disconnecting... please wait before reconnecting.", "warning")
            if progress_callback:
                progress_callback("Connection Blocked", f"Please wait {remaining_cooldown:.1f}s before reconnecting", 0)
            return False

        logging.info(f"Attempting to connect to {mc_ip}...")
        self._ip_address = mc_ip

        if progress_callback:
            progress_callback("Initializing Connection", f"Preparing to connect to {mc_ip}", 0)

        for attempt in range(self._max_connection_attempts):
            if cancel_check and cancel_check():
                logging.info("Connection cancelled by user before attempt")
                self._is_open = False
                self.connection = None
                return False

            attempt_start_time = time.time()
            timeout = self._connection_timeout_seconds[attempt]
            base_progress = 5 + (attempt * 8)

            if attempt == 0:
                self.status_callback(f"Connecting to {mc_ip}...", "info")
                if progress_callback:
                    progress_callback("Establishing Connection", f"Connecting to {mc_ip} (timeout: {timeout}s)", base_progress)
            else:
                self.status_callback(f"Retrying connection (attempt {attempt + 1}/{self._max_connection_attempts})...", "info")
                if progress_callback:
                    progress_callback("Retrying Connection", f"Attempt {attempt + 1}/{self._max_connection_attempts} (timeout: {timeout}s)", base_progress)

            logging.info(f"Network attempt {attempt + 1}/{self._max_connection_attempts} starting with {timeout}s timeout")

            try:
                self.connection = self.create_connection(mc_ip)
                logging.info("Connection object created.")

                open_start_time = time.time()
                connection_succeeded = self._attempt_connection_with_timeout(mc_ip, timeout, cancel_check)
                open_duration = time.time() - open_start_time
                logging.info(f"OpenConnection call took {open_duration:.3f}s")

                if connection_succeeded is self._CANCELLED:
                    logging.info("Connection cancelled by user")
                    self._cleanup_connection_async()
                    self._is_open = False
                    self.connection = None
                    return False

                if not connection_succeeded:
                    logging.warning(f"Connection attempt {attempt + 1} timed out")
                    self._cleanup_connection_async()

                    if attempt < self._max_connection_attempts - 1:
                        for _ in range(10):
                            if cancel_check and cancel_check():
                                logging.info("Connection cancelled by user between retries")
                                self._is_open = False
                                self.connection = None
                                return False
                            time.sleep(0.1)
                        continue
                    else:
                        self.status_callback(f"Connection timed out after {self._max_connection_attempts} attempts", "error")
                        self._is_open = False
                        self._shutting_down = False
                        return False

                logging.info("Connection opened.")

                if progress_callback:
                    progress_callback("Connection Established", "Testing connection...", 30)

                self._is_open = True
                self._shutting_down = False

                probe_start_time = time.time()
                try:
                    self.connection.SetVrValue(66, 0)
                    logging.info("Set VR(66) to 0.")
                    self.connection.SetVrValue(66, 1)
                    logging.info("Set VR(66) to 1.")
                    probe_duration = time.time() - probe_start_time
                    logging.info(f"Connection probe test took {probe_duration:.3f}s")

                    if progress_callback:
                        progress_callback("Verifying Connection", "Connection test successful", 40)
                except Exception as probe_error:
                    probe_duration = time.time() - probe_start_time
                    logging.warning(f"Connection verification failed after {probe_duration:.3f}s: {probe_error}")
                    try:
                        if self.connection:
                            self.connection.CloseConnection()
                    except Exception as close_error:
                        logging.warning(f"Failed to close connection after probe failure: {close_error}")
                    self._is_open = False

                    if attempt < self._max_connection_attempts - 1:
                        self.connection = None
                        attempt_duration = time.time() - attempt_start_time
                        logging.info(f"Network attempt {attempt + 1} failed after {attempt_duration:.3f}s, retrying after 1s delay")
                        time.sleep(1.0)
                        continue
                    else:
                        raise

                logging.info("Successfully connected.")

                if progress_callback:
                    progress_callback("Starting Watchdog", "Initializing connection monitor", 45)

                self._start_watchdog()

                attempt_duration = time.time() - attempt_start_time
                logging.info(f"Network attempt {attempt + 1} succeeded in {attempt_duration:.3f}s")

                if progress_callback:
                    progress_callback("Connection Complete", "Successfully connected to controller", 50)

                self.status_callback("Successfully connected", "info")
                return True

            except TUA.TrioConnectionError as e:
                logging.error(f"TrioConnectionError during connect attempt {attempt + 1}: {str(e)}")

                if attempt < self._max_connection_attempts - 1:
                    self._is_open = False
                    self.connection = None
                    time.sleep(1.0)
                    continue
                else:
                    self.status_callback(f"Connection failed: {str(e)}", "error")
                    self._is_open = False
                    self._shutting_down = False
                    self.connection = None
                    return False

            except Exception as e:
                logging.exception(f"Unexpected error during connect attempt {attempt + 1}: {str(e)}")

                if attempt < self._max_connection_attempts - 1:
                    self._is_open = False
                    self.connection = None
                    time.sleep(1.0)
                    continue
                else:
                    self.status_callback(f"Connection failed: {str(e)}", "error")
                    self._is_open = False
                    self._shutting_down = False
                    self.connection = None
                    return False

        return False

    def disconnect(self):
        logging.info("Attempting to disconnect...")

        try:
            self._stop_watchdog()
        except Exception as e:
            logging.warning(f"Exception stopping watchdog during disconnect: {e}")

        self._shutting_down = True

        if self.connection:
            try:
                self.status_callback("Disconnecting...", "info")
            except Exception as e:
                logging.warning(f"Exception in status callback during disconnect: {e}")

            try:
                if hasattr(self.connection, 'StopEventWorker'):
                    self.connection.StopEventWorker()
                elif hasattr(self.connection, 'stop_event_worker'):
                    self.connection.stop_event_worker()
                elif hasattr(self.connection, 'SignalEventWorker'):
                    self.connection.SignalEventWorker()
            except Exception as e:
                logging.warning(f"Could not signal event worker: {e}")

            try:
                close_done = threading.Event()
                close_error = []

                def _close_thread():
                    try:
                        self.connection.CloseConnection()
                    except Exception as e:
                        close_error.append(e)
                    finally:
                        close_done.set()

                t = threading.Thread(target=_close_thread, name="TrioCloseConn", daemon=True)
                t.start()
                if not close_done.wait(timeout=5.0):
                    logging.warning("CloseConnection() timed out after 5s — abandoning (socket may leak)")
                elif close_error:
                    logging.info(f"Exception during CloseConnection (disconnection successful): {close_error[0]}")
            except Exception as e:
                logging.info(f"Exception during CloseConnection (disconnection successful): {str(e)}")

            self.connection = None
            self._is_open = False
            self._enter_disconnect_cooldown()
            logging.info("Successfully disconnected.")
            return True

        self._is_open = False
        self._shutting_down = False
        logging.info("No active connection to disconnect.")
        return True

    def mark_connection_lost(self) -> bool:
        with self._state_lock:
            if not self._is_open:
                return False
            self._is_open = False
        logging.warning("Connection to controller lost")

        try:
            self._watchdog_stop.set()
        except Exception:
            pass

        self._enter_disconnect_cooldown()

        try:
            if self._on_connection_lost:
                self._on_connection_lost()
        except Exception:
            pass

        return True

    def is_connected(self) -> bool:
        return bool(self.connection) and bool(self._is_open)

    def upload_file(self, local_file: str, remote_file: str,
                    file_type: TUA.FileType = TUA.FileType.BASIC,
                    transfer_option: int = 0,
                    progress_callback: Optional[Callable] = None) -> bool:
        if not self.is_connected():
            logging.error("Cannot upload file: not connected")
            return False

        try:
            logging.info(f"Uploading {local_file} to {remote_file} (type: {file_type})")
            transfer_opt_enum = TUA.FileTransferOption(transfer_option)
            self.connection.UploadFile(
                local_file, remote_file, file_type, transfer_opt_enum,
                progress_callback if progress_callback else None
            )
            logging.info(f"Successfully uploaded {local_file} to {remote_file}")
            return True
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            return False

    def download_file(self, remote_file: str, local_file: str,
                      progress_callback: Optional[Callable] = None) -> bool:
        if not self.is_connected():
            logging.error("Cannot download file: not connected")
            return False

        try:
            logging.info(f"Starting download: {remote_file} -> {local_file}")
            self.connection.DownloadFile(
                local_file, remote_file,
                progress_callback if progress_callback else None
            )
            logging.info(f"Successfully downloaded {remote_file} to {local_file}")
            return True
        except Exception as e:
            logging.error(f"Error downloading file: {e}")
            return False
