import sys
import socket
import threading

maxthreads = 100
buffersize = 4096

threadcount = 0
threadlock = threading.Lock()


def parseurl(url):
    if not url.startswith("http://"):
        raise ValueError("invalid url")

    url = url[7:]
    colonpos = url.find(':')
    slashpos = url.find('/')

    if slashpos == -1:
        slashpos = len(url)

    if colonpos != -1 and colonpos < slashpos:
        host = url[:colonpos]
        port = int(url[colonpos + 1:slashpos])
    else:
        host = url[:slashpos]
        port = 80

    path = url[slashpos:] if slashpos < len(url) else "/"
    return host, port, path


def parserequest(buffer):
    lines = buffer.decode('utf-8', errors='ignore').split('\r\n')
    if not lines:
        raise ValueError("empty request")

    requestline = lines[0].split()
    if len(requestline) != 3:
        raise ValueError("invalid request line")

    method, url, version = requestline

    if version not in ["HTTP/1.0", "HTTP/1.1"]:
        raise ValueError("unsupported version")

    headers_dict = {}
    for line in lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            headers_dict[key.strip().lower()] = value.strip()

    # Case 1: absolute URI
    if url.startswith("http://"):
        host, port, path = parseurl(url)

    # Case 2: relative URI + Host header
    else:
        if "host" not in headers_dict:
            raise ValueError("host header missing")

        host_header = headers_dict["host"]

        if ':' in host_header:
            host, port = host_header.split(':', 1)
            port = int(port)
        else:
            host = host_header
            port = 80

        path = url if url else "/"

    headers = '\r\n'.join(lines[1:]) + '\r\n'

    return method, host, port, path, headers


def senderror(clientsock, code, reason):
    response = f"HTTP/1.0 {code} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    clientsock.sendall(response.encode('utf-8'))


def handleclient(clientsock):
    global threadcount

    try:
        buffer = b''
        while True:
            data = clientsock.recv(buffersize)
            if not data:
                break
            buffer += data
            if b'\r\n\r\n' in buffer:
                break

        if not buffer:
            return

        method, host, port, path, headers = parserequest(buffer)

        if method != "GET":
            senderror(clientsock, 501, "Not Implemented")
            return

        serversock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversock.connect((host, port))

        serverrequest = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        serversock.sendall(serverrequest.encode('utf-8'))

        while True:
            data = serversock.recv(buffersize)
            if not data:
                break
            clientsock.sendall(data)

        serversock.close()

    except Exception:
        senderror(clientsock, 400, "Bad Request")

    finally:
        clientsock.close()
        with threadlock:
            threadcount -= 1


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <port>")
        sys.exit(1)

    port = int(sys.argv[1])

    listensock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listensock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listensock.bind(('', port))
    listensock.listen(socket.SOMAXCONN)

    print(f"proxy running on port {port}")

    global threadcount

    while True:
        clientsock, addr = listensock.accept()

        with threadlock:
            if threadcount >= maxthreads:
                senderror(clientsock, 503, "Service Unavailable")
                clientsock.close()
                continue
            threadcount += 1

        t = threading.Thread(target=handleclient, args=(clientsock,))
        t.daemon = True
        t.start()


if __name__ == "__main__":
    main()