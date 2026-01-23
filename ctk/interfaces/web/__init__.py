"""
Web interface for CTK - serves static SPA with REST API backend
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, send_file, send_from_directory
from flask_cors import CORS

from ctk.interfaces.rest.api import RestInterface


class WebInterface(RestInterface):
    """
    Web interface that extends RestInterface with static file serving.

    Serves a single-page application (SPA) that uses the REST API backend.
    The SPA is served from /web/ and all API endpoints from /api/.

    Usage:
        web = WebInterface(db_path="conversations.db")
        web.run(port=5000)  # Access at http://localhost:5000/
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        static_dir: Optional[str] = None,
    ):
        super().__init__(db_path, config)

        # Determine static files directory
        if static_dir:
            self.static_dir = Path(static_dir)
        else:
            # Default: look for web_frontend.html in examples/
            module_dir = Path(__file__).parent.parent.parent.parent
            self.static_dir = module_dir / "examples"

        # Setup web routes
        self._setup_web_routes()

    def _setup_web_routes(self):
        """Setup routes for serving the web interface"""

        @self.app.route("/")
        def index():
            """Serve the main web interface"""
            frontend_path = self.static_dir / "web_frontend.html"
            if frontend_path.exists():
                return send_file(frontend_path)
            else:
                return (
                    """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>CTK Web Interface</title>
                    <style>
                        body { font-family: sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
                        h1 { color: #667eea; }
                        code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
                        .endpoint { margin: 10px 0; padding: 10px; background: #f7f7f7; border-radius: 5px; }
                        .method { font-weight: bold; color: #5a67d8; }
                    </style>
                </head>
                <body>
                    <h1>CTK REST API</h1>
                    <p>Web frontend not found. API is available at <code>/api/</code></p>

                    <h2>Available Endpoints</h2>

                    <h3>Conversations</h3>
                    <div class="endpoint"><span class="method">GET</span> /api/conversations - List conversations</div>
                    <div class="endpoint"><span class="method">GET</span> /api/conversations/:id - Get conversation</div>
                    <div class="endpoint"><span class="method">POST</span> /api/conversations/search - Search</div>
                    <div class="endpoint"><span class="method">POST</span> /api/conversations/:id/star - Star</div>
                    <div class="endpoint"><span class="method">POST</span> /api/conversations/:id/pin - Pin</div>
                    <div class="endpoint"><span class="method">POST</span> /api/conversations/:id/archive - Archive</div>

                    <h3>Tags</h3>
                    <div class="endpoint"><span class="method">GET</span> /api/tags - List tags</div>
                    <div class="endpoint"><span class="method">POST</span> /api/conversations/:id/tags - Add tags</div>

                    <h3>Views</h3>
                    <div class="endpoint"><span class="method">GET</span> /api/views - List views</div>
                    <div class="endpoint"><span class="method">POST</span> /api/views - Create view</div>
                    <div class="endpoint"><span class="method">GET</span> /api/views/:name/eval - Evaluate view</div>

                    <h3>Metadata</h3>
                    <div class="endpoint"><span class="method">GET</span> /api/models - List models</div>
                    <div class="endpoint"><span class="method">GET</span> /api/sources - List sources</div>
                    <div class="endpoint"><span class="method">GET</span> /api/statistics - Database stats</div>
                </body>
                </html>
                """,
                    200,
                )

        @self.app.route("/static/<path:filename>")
        def serve_static(filename):
            """Serve static files (CSS, JS, images)"""
            static_path = self.static_dir / "static"
            if static_path.exists():
                return send_from_directory(static_path, filename)
            return "Not found", 404


# Convenience function for quick start
def create_app(db_path: str, config: Optional[Dict[str, Any]] = None) -> WebInterface:
    """Create a configured WebInterface application"""
    web = WebInterface(db_path=db_path, config=config)
    web.initialize()
    return web
