from http import server
import os
import threading
from .plugin import JobServerPlugin
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http import HTTPStatus
import multiprocessing, socket


# Thread-safe connection counter
class ConnectionCounter:
    def __init__(self, max_conn=10):
        self._count = 0
        self._max = max_conn
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            if self._count >= self._max:
                return False
            self._count += 1
            return True

    def release(self):
        with self._lock:
            self._count = max(0, self._count - 1)

    @property
    def count(self):
        with self._lock:
            return self._count


# Global counter shared across all handler instances
_connection_counter = ConnectionCounter(max_conn=10)


class mProvHTTPReqestHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.maxConnFileSize = getattr(server, "maxConnFileSize", 0)
        super().__init__(request, client_address, server)

    def checkFileSize(self):
        maxConnFileSize = self.maxConnFileSize
        self.directory = self.server.rootDir
        path = self.translate_path(self.path)
        # only apply to images.
        if not path.startswith("/images/"):
            return True
        if not os.path.isdir(path):
            if path.endswith("/"):
                self.send_error(
                    HTTPStatus.NOT_FOUND, "File not found, filename invalid"
                )
                return False
        else:
            return True
        f = None
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found, unable to open")
            return False
        try:
            fs = os.fstat(f.fileno())
            if fs[6] >= maxConnFileSize:
                if not _connection_counter.acquire():
                    # 404 will result in a retry from the mPCC/client hopefully to another server.
                    self.send_error(
                        HTTPStatus.NOT_FOUND, "File not found, max connections reached"
                    )
                    if self.server.js is not None:
                        self.server.js.register = False
                    return False
        except:
            f.close()
            raise
        return True

    def do_GET(self):
        print(_connection_counter.count)

        if (
            os.getloadavg()[1] >= multiprocessing.cpu_count()
            and self.server.js.config_data["loadmon"]
            and self.path.startswith("/images/")
        ):
            print("Not Serving, high load.")
            self.send_error(HTTPStatus.NOT_FOUND, "Unable to serve, High load")
            return False

        retVal = None
        if self.checkFileSize():
            # we are ok to serve.
            try:
                retVal = super().do_GET()
            finally:
                _connection_counter.release()
                if _connection_counter.count < 10:  # maxConn
                    if self.server.js is not None:
                        self.server.js.register = True

        return retVal

    def do_HEAD(self):
        if not self.checkFileSize():
            return None
        return super().do_HEAD()


class mProvHTTPServer(ThreadingHTTPServer):
    rootDir = ""
    maxConnFileSize = 0
    js = None

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        if ":" in server_address[0]:
            # we have an IPv6 bind address
            self.address_family = socket.AF_INET6
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        # self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)


class mprov_webserver(JobServerPlugin):
    jobModule = "mprov-webserver"
    hostName = "::"
    serverPort = 8080
    serverInstance = None
    rootDir = ""
    maxConnFileSize = 0

    def handle_jobs(self):
        print(f"Starting mProv Webserver on port {self.serverPort}...")

        serverInstance = mProvHTTPServer(
            (self.hostName, self.serverPort), mProvHTTPReqestHandler
        )
        serverInstance.rootDir = self.rootDir
        serverInstance.timeout = 0.5
        serverInstance.js = self.js
        serverInstance.maxConnFileSize = self.maxConnFileSize

        # this should allow us to exit out ok.
        while self.js.running:
            serverInstance.handle_request()

        print("Stopping mProv Webserver.")
