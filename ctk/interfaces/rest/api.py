"""
RESTful API implementation for CTK
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from ctk.core import registry
from ctk.core.models import ConversationTree
from ctk.interfaces.base import (BaseInterface, InterfaceResponse,
                                 ResponseStatus)


class RestInterface(BaseInterface):
    """RESTful API interface using Flask"""

    def __init__(
        self, db_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(db_path, config)
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for web frontends

        # Configure Flask
        self.app.config.update(config or {})

        # Setup routes
        self._setup_routes()

    def initialize(self) -> InterfaceResponse:
        """Initialize the REST API server"""
        try:
            # Setup logging
            logging.basicConfig(level=logging.INFO)

            # Initialize database if path provided
            if self.db_path and not self._db:
                self._db = self.db

            return InterfaceResponse.success(
                message="REST API initialized successfully"
            )
        except Exception as e:
            return self.handle_error(e)

    def shutdown(self) -> InterfaceResponse:
        """Shutdown the REST API server"""
        try:
            if self._db:
                self._db.close()
            return InterfaceResponse.success(message="REST API shutdown successfully")
        except Exception as e:
            return self.handle_error(e)

    def run(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
        """Run the Flask server"""
        self.app.run(host=host, port=port, debug=debug)

    def _setup_routes(self):
        """Setup all API routes"""

        @self.app.route("/api/health", methods=["GET"])
        def health_check():
            """Health check endpoint"""
            return jsonify({"status": "healthy", "service": "ctk-api"})

        @self.app.route("/api/conversations", methods=["GET"])
        def list_conversations_route():
            """List conversations with pagination and filters"""
            limit = request.args.get("limit", 100, type=int)
            offset = request.args.get("offset", 0, type=int)
            sort_by = request.args.get("sort_by", "updated_at")

            filters = {}
            if request.args.get("source"):
                filters["source"] = request.args.get("source")
            if request.args.get("model"):
                filters["model"] = request.args.get("model")
            if request.args.get("project"):
                filters["project"] = request.args.get("project")
            if request.args.get("tags"):
                filters["tags"] = request.args.get("tags").split(",")

            response = self.list_conversations(limit, offset, sort_by, filters)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>", methods=["GET"])
        def get_conversation_route(conversation_id: str):
            """Get a specific conversation"""
            include_paths = request.args.get("include_paths", "false").lower() == "true"
            response = self.get_conversation(conversation_id, include_paths)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>", methods=["PATCH"])
        def update_conversation_route(conversation_id: str):
            """Update conversation metadata"""
            updates = request.get_json()
            response = self.update_conversation(conversation_id, updates)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
        def delete_conversation_route(conversation_id: str):
            """Delete a conversation"""
            response = self.delete_conversation(conversation_id)
            return self._format_response(response)

        @self.app.route("/api/conversations/search", methods=["POST"])
        def search_conversations_route():
            """Search conversations with advanced filters"""
            data = request.get_json()
            query = data.get("query", "")
            limit = data.get("limit", 100)
            offset = data.get("offset", 0)

            # Advanced search options
            options = {
                "title_only": data.get("title_only", False),
                "content_only": data.get("content_only", False),
                "date_from": data.get("date_from"),
                "date_to": data.get("date_to"),
                "min_messages": data.get("min_messages"),
                "max_messages": data.get("max_messages"),
                "has_branches": data.get("has_branches"),
                "source": data.get("source"),
                "model": data.get("model"),
                "project": data.get("project"),
                "tags": data.get("tags"),
                "starred": data.get("starred"),
                "pinned": data.get("pinned"),
                "archived": data.get("archived"),
                "order_by": data.get("order_by", "updated_at"),
                "ascending": data.get("ascending", False),
            }

            response = self.search_conversations(query, limit, options, offset=offset)
            return self._format_response(response)

        @self.app.route("/api/import", methods=["POST"])
        def import_conversations_route():
            """Import conversations from uploaded file or JSON data"""
            if "file" in request.files:
                # Handle file upload
                file = request.files["file"]
                format_type = request.form.get("format")
                tags = (
                    request.form.get("tags", "").split(",")
                    if request.form.get("tags")
                    else None
                )

                # Save uploaded file temporarily
                import tempfile

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=file.filename
                ) as tmp:
                    file.save(tmp.name)
                    response = self.import_conversations(tmp.name, format_type, tags)

                return self._format_response(response)
            else:
                # Handle JSON data
                data = request.get_json()
                source = data.get("data")
                format_type = data.get("format")
                tags = data.get("tags")

                response = self.import_conversations(source, format_type, tags)
                return self._format_response(response)

        @self.app.route("/api/export", methods=["POST"])
        def export_conversations_route():
            """Export conversations to specified format"""
            data = request.get_json()
            format_type = data.get("format", "jsonl")
            conversation_ids = data.get("conversation_ids")
            filters = data.get("filters", {})

            # Export to string (not file)
            response = self.export_conversations(
                None,  # No output file, return as string
                format_type,
                conversation_ids,
                filters,
            )

            if response.status == ResponseStatus.SUCCESS:
                # Return the exported data directly
                if format_type in ["json", "jsonl"]:
                    return Response(
                        response.data,
                        mimetype="application/json",
                        headers={
                            "Content-Disposition": f"attachment; filename=export.{format_type}"
                        },
                    )
                elif format_type == "markdown":
                    return Response(
                        response.data,
                        mimetype="text/markdown",
                        headers={
                            "Content-Disposition": "attachment; filename=export.md"
                        },
                    )
                else:
                    return Response(
                        response.data,
                        mimetype="text/plain",
                        headers={
                            "Content-Disposition": f"attachment; filename=export.{format_type}"
                        },
                    )
            else:
                return self._format_response(response)

        @self.app.route("/api/statistics", methods=["GET"])
        def get_statistics_route():
            """Get database statistics"""
            response = self.get_statistics()
            return self._format_response(response)

        @self.app.route("/api/plugins", methods=["GET"])
        def list_plugins():
            """List available plugins"""
            importers = registry.list_importers()
            exporters = registry.list_exporters()

            return jsonify(
                {
                    "importers": [
                        {"name": i.name, "description": i.description}
                        for i in importers
                    ],
                    "exporters": [
                        {"name": e.name, "description": e.description}
                        for e in exporters
                    ],
                }
            )

        # ============================================================
        # Organization Endpoints
        # ============================================================

        @self.app.route("/api/conversations/<conversation_id>/star", methods=["POST"])
        def star_conversation_route(conversation_id: str):
            """Star a conversation"""
            response = self.star_conversation(conversation_id, star=True)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/star", methods=["DELETE"])
        def unstar_conversation_route(conversation_id: str):
            """Unstar a conversation"""
            response = self.star_conversation(conversation_id, star=False)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/pin", methods=["POST"])
        def pin_conversation_route(conversation_id: str):
            """Pin a conversation"""
            response = self.pin_conversation(conversation_id, pin=True)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/pin", methods=["DELETE"])
        def unpin_conversation_route(conversation_id: str):
            """Unpin a conversation"""
            response = self.pin_conversation(conversation_id, pin=False)
            return self._format_response(response)

        @self.app.route(
            "/api/conversations/<conversation_id>/archive", methods=["POST"]
        )
        def archive_conversation_route(conversation_id: str):
            """Archive a conversation"""
            response = self.archive_conversation(conversation_id, archive=True)
            return self._format_response(response)

        @self.app.route(
            "/api/conversations/<conversation_id>/archive", methods=["DELETE"]
        )
        def unarchive_conversation_route(conversation_id: str):
            """Unarchive a conversation"""
            response = self.archive_conversation(conversation_id, archive=False)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/title", methods=["PUT"])
        def rename_conversation_route(conversation_id: str):
            """Rename a conversation"""
            data = request.get_json()
            title = data.get("title", "")
            response = self.rename_conversation(conversation_id, title)
            return self._format_response(response)

        @self.app.route(
            "/api/conversations/<conversation_id>/duplicate", methods=["POST"]
        )
        def duplicate_conversation_route(conversation_id: str):
            """Duplicate a conversation"""
            data = request.get_json() or {}
            new_title = data.get("title")
            response = self.duplicate_conversation(conversation_id, new_title)
            return self._format_response(response)

        # ============================================================
        # Tag Management Endpoints
        # ============================================================

        @self.app.route("/api/tags", methods=["GET"])
        def list_tags_route():
            """List all tags with counts"""
            response = self.list_tags()
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/tags", methods=["POST"])
        def add_tags_route(conversation_id: str):
            """Add tags to a conversation"""
            data = request.get_json()
            tags = data.get("tags", [])
            response = self.add_tags(conversation_id, tags)
            return self._format_response(response)

        @self.app.route(
            "/api/conversations/<conversation_id>/tags/<tag>", methods=["DELETE"]
        )
        def remove_tag_route(conversation_id: str, tag: str):
            """Remove a tag from a conversation"""
            response = self.remove_tag(conversation_id, tag)
            return self._format_response(response)

        @self.app.route("/api/tags/<path:tag>/conversations", methods=["GET"])
        def list_conversations_by_tag_route(tag: str):
            """List conversations with a specific tag"""
            limit = request.args.get("limit", 100, type=int)
            offset = request.args.get("offset", 0, type=int)
            response = self.list_conversations_by_tag(tag, limit, offset)
            return self._format_response(response)

        # ============================================================
        # Metadata Endpoints
        # ============================================================

        @self.app.route("/api/models", methods=["GET"])
        def list_models_route():
            """List all models with counts"""
            response = self.list_models()
            return self._format_response(response)

        @self.app.route("/api/sources", methods=["GET"])
        def list_sources_route():
            """List all sources with counts"""
            response = self.list_sources()
            return self._format_response(response)

        @self.app.route("/api/timeline", methods=["GET"])
        def get_timeline_route():
            """Get conversation timeline/analytics"""
            granularity = request.args.get("granularity", "day")
            limit = request.args.get("limit", 30, type=int)
            response = self.get_timeline(granularity, limit)
            return self._format_response(response)

        # ============================================================
        # Tree/Path Endpoints
        # ============================================================

        @self.app.route("/api/conversations/<conversation_id>/tree", methods=["GET"])
        def get_conversation_tree_route(conversation_id: str):
            """Get conversation tree structure"""
            response = self.get_conversation_tree(conversation_id)
            return self._format_response(response)

        @self.app.route("/api/conversations/<conversation_id>/paths", methods=["GET"])
        def list_conversation_paths_route(conversation_id: str):
            """List all paths in a conversation"""
            response = self.list_conversation_paths(conversation_id)
            return self._format_response(response)

        @self.app.route(
            "/api/conversations/<conversation_id>/paths/<int:path_index>",
            methods=["GET"],
        )
        def get_conversation_path_route(conversation_id: str, path_index: int):
            """Get a specific path from a conversation"""
            response = self.get_conversation_path(conversation_id, path_index)
            return self._format_response(response)

        # ============================================================
        # Views Endpoints
        # ============================================================

        @self.app.route("/api/views", methods=["GET"])
        def list_views_route():
            """List all views"""
            response = self.list_views()
            return self._format_response(response)

        @self.app.route("/api/views", methods=["POST"])
        def create_view_route():
            """Create a new view"""
            content_type = request.content_type or ""
            if "yaml" in content_type:
                # YAML body
                yaml_content = request.get_data(as_text=True)
                response = self.create_view_from_yaml(yaml_content)
            else:
                # JSON body
                data = request.get_json()
                response = self.create_view(data)
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>", methods=["GET"])
        def get_view_route(view_name: str):
            """Get view definition"""
            format_type = request.args.get("format", "json")
            response = self.get_view(view_name, format_type)
            if response.status == ResponseStatus.SUCCESS and format_type == "yaml":
                return Response(response.data, mimetype="text/yaml")
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>", methods=["PUT"])
        def update_view_route(view_name: str):
            """Update a view"""
            content_type = request.content_type or ""
            if "yaml" in content_type:
                yaml_content = request.get_data(as_text=True)
                response = self.update_view_from_yaml(view_name, yaml_content)
            else:
                data = request.get_json()
                response = self.update_view(view_name, data)
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>", methods=["DELETE"])
        def delete_view_route(view_name: str):
            """Delete a view"""
            response = self.delete_view(view_name)
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>/eval", methods=["GET"])
        def evaluate_view_route(view_name: str):
            """Evaluate view and return resolved conversations"""
            response = self.evaluate_view(view_name)
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>/conversations", methods=["POST"])
        def add_to_view_route(view_name: str):
            """Add conversations to a view"""
            data = request.get_json()
            conversation_ids = data.get("conversation_ids", [])
            options = data.get("options", {})
            response = self.add_to_view(view_name, conversation_ids, options)
            return self._format_response(response)

        @self.app.route(
            "/api/views/<view_name>/conversations/<conversation_id>", methods=["DELETE"]
        )
        def remove_from_view_route(view_name: str, conversation_id: str):
            """Remove a conversation from a view"""
            response = self.remove_from_view(view_name, conversation_id)
            return self._format_response(response)

        @self.app.route("/api/views/<view_name>/check", methods=["GET"])
        def check_view_route(view_name: str):
            """Validate view and check for drift"""
            response = self.check_view(view_name)
            return self._format_response(response)

    def _format_response(self, response: InterfaceResponse) -> Response:
        """Format InterfaceResponse for Flask"""
        status_code_map = {
            ResponseStatus.SUCCESS: 200,
            ResponseStatus.ERROR: 400,
            ResponseStatus.WARNING: 200,
            ResponseStatus.INFO: 200,
        }

        return jsonify(response.to_dict()), status_code_map.get(response.status, 200)

    # Implement abstract methods from BaseInterface

    def import_conversations(
        self,
        source: Union[str, Dict, List],
        format: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> InterfaceResponse:
        """Import conversations"""
        try:
            # Use registry to import
            if isinstance(source, str):
                # File path
                conversations = registry.import_file(source, format=format)
            else:
                # Direct data
                importer = registry.get_importer(format)
                if not importer:
                    return InterfaceResponse.error(
                        f"No importer found for format: {format}"
                    )
                conversations = importer.import_data(source)

            # Add tags if specified
            if tags:
                for conv in conversations:
                    conv.metadata.tags.extend(tags)

            # Save to database
            if self.db:
                with self.db as db:
                    for conv in conversations:
                        db.save_conversation(conv)

            return InterfaceResponse.success(
                data={"imported": len(conversations)},
                message=f"Successfully imported {len(conversations)} conversations",
            )
        except Exception as e:
            return self.handle_error(e)

    def export_conversations(
        self,
        output: Optional[str],
        format: str = "jsonl",
        conversation_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> InterfaceResponse:
        """Export conversations"""
        try:
            # Get conversations from database
            conversations = []
            if self.db:
                with self.db as db:
                    if conversation_ids:
                        for conv_id in conversation_ids:
                            conv = db.load_conversation(conv_id)
                            if conv:
                                conversations.append(conv)
                    else:
                        # Get all with filters
                        query = db.session.query(db.ConversationModel)

                        if filters:
                            query = self.apply_filters(query, filters)

                        for conv_model in query.all():
                            conv = db._model_to_tree(conv_model)
                            conversations.append(conv)

            # Export using registry
            exporter = registry.get_exporter(format)
            if not exporter:
                return InterfaceResponse.error(
                    f"No exporter found for format: {format}"
                )

            exported_data = exporter.export_conversations(
                conversations, output_file=output, **kwargs
            )

            return InterfaceResponse.success(
                data=exported_data,
                message=f"Successfully exported {len(conversations)} conversations",
            )
        except Exception as e:
            return self.handle_error(e)

    def search_conversations(
        self,
        query: str,
        limit: int = 100,
        options: Optional[Dict[str, Any]] = None,
        offset: int = 0,
        **kwargs,
    ) -> InterfaceResponse:
        """Search conversations with advanced filters"""
        try:
            results = []
            total = 0
            options = options or {}

            if self.db:
                with self.db as db:
                    # Use advanced search with all options
                    results = db.search_conversations(
                        query_text=query,
                        limit=limit,
                        offset=offset,
                        title_only=options.get("title_only", False),
                        content_only=options.get("content_only", False),
                        date_from=options.get("date_from"),
                        date_to=options.get("date_to"),
                        source=options.get("source"),
                        project=options.get("project"),
                        model=options.get("model"),
                        tags=options.get("tags"),
                        min_messages=options.get("min_messages"),
                        max_messages=options.get("max_messages"),
                        has_branches=options.get("has_branches"),
                        archived=options.get("archived"),
                        starred=options.get("starred"),
                        pinned=options.get("pinned"),
                        order_by=options.get("order_by", "updated_at"),
                        ascending=options.get("ascending", False),
                    )
                    total = len(results)

            return InterfaceResponse.success(
                data={
                    "conversations": [r.to_dict() for r in results],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
                message=f"Found {len(results)} conversations",
            )
        except Exception as e:
            return self.handle_error(e)

    def list_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> InterfaceResponse:
        """List conversations"""
        try:
            conversations = []
            total = 0

            if self.db:
                with self.db as db:
                    query = db.session.query(db.ConversationModel)

                    if filters:
                        query = self.apply_filters(query, filters)

                    # Get total count
                    total = query.count()

                    # Apply sorting
                    if hasattr(db.ConversationModel, sort_by):
                        query = query.order_by(
                            getattr(db.ConversationModel, sort_by).desc()
                        )

                    # Apply pagination
                    query = query.limit(limit).offset(offset)

                    for conv_model in query.all():
                        conversations.append(conv_model.to_dict())

            return InterfaceResponse.success(
                data={
                    "conversations": conversations,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            )
        except Exception as e:
            return self.handle_error(e)

    def get_conversation(
        self, conversation_id: str, include_paths: bool = False, **kwargs
    ) -> InterfaceResponse:
        """Get a specific conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv = db.load_conversation(conversation_id)

                if not conv:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                data = {
                    "id": conv.id,
                    "title": conv.title,
                    "metadata": conv.metadata.to_dict(),
                    "message_count": len(conv.message_map),
                }

                if include_paths:
                    data["paths"] = []
                    for i, path in enumerate(conv.get_all_paths()):
                        data["paths"].append(
                            {
                                "path_id": i,
                                "length": len(path),
                                "messages": [m.to_dict() for m in path],
                            }
                        )
                else:
                    # Just include the longest path
                    data["messages"] = [m.to_dict() for m in conv.get_longest_path()]

            return InterfaceResponse.success(data=data)
        except Exception as e:
            return self.handle_error(e)

    def update_conversation(
        self, conversation_id: str, updates: Dict[str, Any], **kwargs
    ) -> InterfaceResponse:
        """Update conversation metadata"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv_model = (
                    db.session.query(db.ConversationModel)
                    .filter_by(id=conversation_id)
                    .first()
                )

                if not conv_model:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                # Update allowed fields
                if "title" in updates:
                    conv_model.title = updates["title"]
                if "tags" in updates:
                    # Handle tag updates
                    pass
                if "project" in updates:
                    conv_model.project = updates["project"]

                db.session.commit()

            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} updated"
            )
        except Exception as e:
            return self.handle_error(e)

    def delete_conversation(self, conversation_id: str, **kwargs) -> InterfaceResponse:
        """Delete a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.delete_conversation(conversation_id)

            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} deleted"
            )
        except Exception as e:
            return self.handle_error(e)

    def get_statistics(self, **kwargs) -> InterfaceResponse:
        """Get database statistics"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                stats = db.get_statistics()

            return InterfaceResponse.success(data=stats)
        except Exception as e:
            return self.handle_error(e)

    # ================================================================
    # Organization Methods
    # ================================================================

    def star_conversation(
        self, conversation_id: str, star: bool = True
    ) -> InterfaceResponse:
        """Star or unstar a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.star_conversation(conversation_id, star=star)

            action = "starred" if star else "unstarred"
            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} {action}"
            )
        except Exception as e:
            return self.handle_error(e)

    def pin_conversation(
        self, conversation_id: str, pin: bool = True
    ) -> InterfaceResponse:
        """Pin or unpin a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.pin_conversation(conversation_id, pin=pin)

            action = "pinned" if pin else "unpinned"
            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} {action}"
            )
        except Exception as e:
            return self.handle_error(e)

    def archive_conversation(
        self, conversation_id: str, archive: bool = True
    ) -> InterfaceResponse:
        """Archive or unarchive a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.archive_conversation(conversation_id, archive=archive)

            action = "archived" if archive else "unarchived"
            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} {action}"
            )
        except Exception as e:
            return self.handle_error(e)

    def rename_conversation(
        self, conversation_id: str, title: str
    ) -> InterfaceResponse:
        """Rename a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.update_conversation_metadata(conversation_id, title=title)

            return InterfaceResponse.success(
                message=f"Conversation {conversation_id} renamed to '{title}'"
            )
        except Exception as e:
            return self.handle_error(e)

    def duplicate_conversation(
        self, conversation_id: str, new_title: Optional[str] = None
    ) -> InterfaceResponse:
        """Duplicate a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                new_conv = db.duplicate_conversation(
                    conversation_id, new_title=new_title
                )

            return InterfaceResponse.success(
                data={"new_conversation_id": new_conv.id if new_conv else None},
                message=f"Conversation duplicated",
            )
        except Exception as e:
            return self.handle_error(e)

    # ================================================================
    # Tag Management Methods
    # ================================================================

    def list_tags(self) -> InterfaceResponse:
        """List all tags with counts"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                tags = db.get_all_tags(with_counts=True)

            return InterfaceResponse.success(data={"tags": tags})
        except Exception as e:
            return self.handle_error(e)

    def add_tags(self, conversation_id: str, tags: List[str]) -> InterfaceResponse:
        """Add tags to a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.add_tags(conversation_id, tags)

            return InterfaceResponse.success(
                message=f"Added {len(tags)} tags to conversation {conversation_id}"
            )
        except Exception as e:
            return self.handle_error(e)

    def remove_tag(self, conversation_id: str, tag: str) -> InterfaceResponse:
        """Remove a tag from a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.remove_tag(conversation_id, tag)

            return InterfaceResponse.success(
                message=f"Removed tag '{tag}' from conversation {conversation_id}"
            )
        except Exception as e:
            return self.handle_error(e)

    def list_conversations_by_tag(
        self, tag: str, limit: int = 100, offset: int = 0
    ) -> InterfaceResponse:
        """List conversations with a specific tag"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conversations = db.list_conversations_by_tag(tag)
                # Apply pagination manually
                total = len(conversations)
                conversations = conversations[offset : offset + limit]

            return InterfaceResponse.success(
                data={
                    "conversations": [
                        c.to_dict() if hasattr(c, "to_dict") else c
                        for c in conversations
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            )
        except Exception as e:
            return self.handle_error(e)

    # ================================================================
    # Metadata Methods
    # ================================================================

    def list_models(self) -> InterfaceResponse:
        """List all models with counts"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                models = db.get_models()

            return InterfaceResponse.success(data={"models": models})
        except Exception as e:
            return self.handle_error(e)

    def list_sources(self) -> InterfaceResponse:
        """List all sources with counts"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                sources = db.get_sources()

            return InterfaceResponse.success(data={"sources": sources})
        except Exception as e:
            return self.handle_error(e)

    def get_timeline(
        self, granularity: str = "day", limit: int = 30
    ) -> InterfaceResponse:
        """Get conversation timeline/analytics"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                timeline = db.get_conversation_timeline(
                    granularity=granularity, limit=limit
                )

            return InterfaceResponse.success(data={"timeline": timeline})
        except Exception as e:
            return self.handle_error(e)

    # ================================================================
    # Tree/Path Methods
    # ================================================================

    def get_conversation_tree(self, conversation_id: str) -> InterfaceResponse:
        """Get conversation tree structure"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv = db.load_conversation(conversation_id)
                if not conv:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                # Build tree structure
                def build_tree_node(message):
                    children = conv.get_children(message.id)
                    return {
                        "id": message.id,
                        "role": (
                            message.role.value
                            if hasattr(message.role, "value")
                            else str(message.role)
                        ),
                        "preview": (
                            (message.content.text[:100] + "...")
                            if message.content.text and len(message.content.text) > 100
                            else (message.content.text or "")
                        ),
                        "children": [build_tree_node(c) for c in children],
                    }

                # Get root messages from IDs
                root_messages = [
                    conv.message_map[mid]
                    for mid in conv.root_message_ids
                    if mid in conv.message_map
                ]

                tree = {
                    "id": conv.id,
                    "title": conv.title,
                    "branch_count": conv.count_branches(),
                    "path_count": len(conv.get_all_paths()),
                    "roots": [build_tree_node(m) for m in root_messages],
                }

            return InterfaceResponse.success(data=tree)
        except Exception as e:
            return self.handle_error(e)

    def list_conversation_paths(self, conversation_id: str) -> InterfaceResponse:
        """List all paths in a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv = db.load_conversation(conversation_id)
                if not conv:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                paths = []
                for i, path in enumerate(conv.get_all_paths()):
                    paths.append(
                        {
                            "path_index": i,
                            "length": len(path),
                            "message_ids": [m.id for m in path],
                            "preview": (
                                f"{path[0].content.text[:50]}..."
                                if path and path[0].content.text
                                else ""
                            ),
                        }
                    )

            return InterfaceResponse.success(data={"paths": paths, "total": len(paths)})
        except Exception as e:
            return self.handle_error(e)

    def get_conversation_path(
        self, conversation_id: str, path_index: int
    ) -> InterfaceResponse:
        """Get a specific path from a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv = db.load_conversation(conversation_id)
                if not conv:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                paths = conv.get_all_paths()
                if path_index < 0 or path_index >= len(paths):
                    return InterfaceResponse.error(
                        f"Path index {path_index} out of range (0-{len(paths)-1})"
                    )

                path = paths[path_index]
                path_data = {
                    "path_index": path_index,
                    "length": len(path),
                    "messages": [m.to_dict() for m in path],
                }

            return InterfaceResponse.success(data=path_data)
        except Exception as e:
            return self.handle_error(e)

    # ================================================================
    # Views Methods
    # ================================================================

    def _get_view_store(self):
        """Get or create ViewStore for this database"""
        if not self.db_path:
            return None
        from ctk.core.views import ViewStore

        return ViewStore(self.db_path)

    def list_views(self) -> InterfaceResponse:
        """List all views"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            views = view_store.list_views_detailed()
            return InterfaceResponse.success(data={"views": views})
        except Exception as e:
            return self.handle_error(e)

    def create_view(self, data: Dict[str, Any]) -> InterfaceResponse:
        """Create a new view from JSON data"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            name = data.get("name")
            if not name:
                return InterfaceResponse.error("View name is required")

            title = data.get("title", name)
            description = data.get("description", "")

            view = view_store.create_view(name, title=title, description=description)
            view_store.save(view)

            return InterfaceResponse.success(
                data={"name": name}, message=f"View '{name}' created"
            )
        except Exception as e:
            return self.handle_error(e)

    def create_view_from_yaml(self, yaml_content: str) -> InterfaceResponse:
        """Create a new view from YAML content"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            import yaml

            data = yaml.safe_load(yaml_content)
            name = data.get("name")
            if not name:
                return InterfaceResponse.error("View name is required in YAML")

            from ctk.core.views import View

            view = View.from_dict(data)
            view_store.save(view)

            return InterfaceResponse.success(
                data={"name": name}, message=f"View '{name}' created from YAML"
            )
        except Exception as e:
            return self.handle_error(e)

    def get_view(self, view_name: str, format_type: str = "json") -> InterfaceResponse:
        """Get view definition"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            view = view_store.load(view_name)
            if not view:
                return InterfaceResponse.error(f"View '{view_name}' not found")

            if format_type == "yaml":
                import yaml

                return InterfaceResponse.success(
                    data=yaml.dump(view.to_dict(), default_flow_style=False)
                )
            else:
                return InterfaceResponse.success(data=view.to_dict())
        except Exception as e:
            return self.handle_error(e)

    def update_view(self, view_name: str, data: Dict[str, Any]) -> InterfaceResponse:
        """Update a view from JSON data"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            view = view_store.load(view_name)
            if not view:
                return InterfaceResponse.error(f"View '{view_name}' not found")

            # Update fields
            if "title" in data:
                view.title = data["title"]
            if "description" in data:
                view.description = data["description"]

            view_store.save(view)
            return InterfaceResponse.success(message=f"View '{view_name}' updated")
        except Exception as e:
            return self.handle_error(e)

    def update_view_from_yaml(
        self, view_name: str, yaml_content: str
    ) -> InterfaceResponse:
        """Update a view from YAML content"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            import yaml

            data = yaml.safe_load(yaml_content)

            from ctk.core.views import View

            view = View.from_dict(data)
            view.name = view_name  # Ensure name matches URL
            view_store.save(view)

            return InterfaceResponse.success(
                message=f"View '{view_name}' updated from YAML"
            )
        except Exception as e:
            return self.handle_error(e)

    def delete_view(self, view_name: str) -> InterfaceResponse:
        """Delete a view"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            if not view_store.load(view_name):
                return InterfaceResponse.error(f"View '{view_name}' not found")

            view_store.delete(view_name)
            return InterfaceResponse.success(message=f"View '{view_name}' deleted")
        except Exception as e:
            return self.handle_error(e)

    def evaluate_view(self, view_name: str) -> InterfaceResponse:
        """Evaluate view and return resolved conversations"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                evaluated = view_store.evaluate(view_name, db)
                if not evaluated:
                    return InterfaceResponse.error(f"View '{view_name}' not found")

                items = []
                for item in evaluated.items:
                    items.append(
                        {
                            "conversation_id": item.conversation_id,
                            "title": item.title_override,
                            "annotation": item.annotation,
                            "path": item.path,
                        }
                    )

            return InterfaceResponse.success(
                data={
                    "name": view_name,
                    "title": evaluated.title,
                    "item_count": len(items),
                    "items": items,
                }
            )
        except Exception as e:
            return self.handle_error(e)

    def add_to_view(
        self,
        view_name: str,
        conversation_ids: List[str],
        options: Dict[str, Any] = None,
    ) -> InterfaceResponse:
        """Add conversations to a view"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            options = options or {}
            for conv_id in conversation_ids:
                view_store.add_to_view(
                    view_name,
                    conv_id,
                    title_override=options.get("title"),
                    annotation=options.get("annotation"),
                    path=options.get("path"),
                )

            return InterfaceResponse.success(
                message=f"Added {len(conversation_ids)} conversations to view '{view_name}'"
            )
        except Exception as e:
            return self.handle_error(e)

    def remove_from_view(
        self, view_name: str, conversation_id: str
    ) -> InterfaceResponse:
        """Remove a conversation from a view"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            view_store.remove_from_view(view_name, conversation_id)
            return InterfaceResponse.success(
                message=f"Removed conversation from view '{view_name}'"
            )
        except Exception as e:
            return self.handle_error(e)

    def check_view(self, view_name: str) -> InterfaceResponse:
        """Validate view and check for drift"""
        try:
            view_store = self._get_view_store()
            if not view_store:
                return InterfaceResponse.error("Database not initialized")

            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                result = view_store.check_view(view_name, db)
                if result is None:
                    return InterfaceResponse.error(f"View '{view_name}' not found")

            return InterfaceResponse.success(data=result)
        except Exception as e:
            return self.handle_error(e)
