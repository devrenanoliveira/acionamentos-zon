import http.server
import os
import socketserver

port = int(os.environ.get('PORT', 8000))
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)

Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(('', port), Handler) as httpd:
    httpd.serve_forever()
