"""
RESTful API implementation for CTK
"""

import json
from typing import Dict, List, Optional, Any, Union
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import logging

from ctk.interfaces.base import BaseInterface, InterfaceResponse, ResponseStatus
from ctk.core import registry
from ctk.core.models import ConversationTree


class RestInterface(BaseInterface):
    """RESTful API interface using Flask"""

    def __init__(self, db_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
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

            return InterfaceResponse.success(message="REST API initialized successfully")
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

        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({"status": "healthy", "service": "ctk-api"})

        @self.app.route('/api/conversations', methods=['GET'])
        def list_conversations_route():
            """List conversations with pagination and filters"""
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            sort_by = request.args.get('sort_by', 'updated_at')

            filters = {}
            if request.args.get('source'):
                filters['source'] = request.args.get('source')
            if request.args.get('model'):
                filters['model'] = request.args.get('model')
            if request.args.get('project'):
                filters['project'] = request.args.get('project')
            if request.args.get('tags'):
                filters['tags'] = request.args.get('tags').split(',')

            response = self.list_conversations(limit, offset, sort_by, filters)
            return self._format_response(response)

        @self.app.route('/api/conversations/<conversation_id>', methods=['GET'])
        def get_conversation_route(conversation_id: str):
            """Get a specific conversation"""
            include_paths = request.args.get('include_paths', 'false').lower() == 'true'
            response = self.get_conversation(conversation_id, include_paths)
            return self._format_response(response)

        @self.app.route('/api/conversations/<conversation_id>', methods=['PATCH'])
        def update_conversation_route(conversation_id: str):
            """Update conversation metadata"""
            updates = request.get_json()
            response = self.update_conversation(conversation_id, updates)
            return self._format_response(response)

        @self.app.route('/api/conversations/<conversation_id>', methods=['DELETE'])
        def delete_conversation_route(conversation_id: str):
            """Delete a conversation"""
            response = self.delete_conversation(conversation_id)
            return self._format_response(response)

        @self.app.route('/api/conversations/search', methods=['POST'])
        def search_conversations_route():
            """Search conversations"""
            data = request.get_json()
            query = data.get('query', '')
            limit = data.get('limit', 100)
            filters = data.get('filters', {})

            response = self.search_conversations(query, limit, filters)
            return self._format_response(response)

        @self.app.route('/api/import', methods=['POST'])
        def import_conversations_route():
            """Import conversations from uploaded file or JSON data"""
            if 'file' in request.files:
                # Handle file upload
                file = request.files['file']
                format_type = request.form.get('format')
                tags = request.form.get('tags', '').split(',') if request.form.get('tags') else None

                # Save uploaded file temporarily
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
                    file.save(tmp.name)
                    response = self.import_conversations(tmp.name, format_type, tags)

                return self._format_response(response)
            else:
                # Handle JSON data
                data = request.get_json()
                source = data.get('data')
                format_type = data.get('format')
                tags = data.get('tags')

                response = self.import_conversations(source, format_type, tags)
                return self._format_response(response)

        @self.app.route('/api/export', methods=['POST'])
        def export_conversations_route():
            """Export conversations to specified format"""
            data = request.get_json()
            format_type = data.get('format', 'jsonl')
            conversation_ids = data.get('conversation_ids')
            filters = data.get('filters', {})

            # Export to string (not file)
            response = self.export_conversations(
                None,  # No output file, return as string
                format_type,
                conversation_ids,
                filters
            )

            if response.status == ResponseStatus.SUCCESS:
                # Return the exported data directly
                if format_type in ['json', 'jsonl']:
                    return Response(
                        response.data,
                        mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=export.{format_type}'}
                    )
                elif format_type == 'markdown':
                    return Response(
                        response.data,
                        mimetype='text/markdown',
                        headers={'Content-Disposition': 'attachment; filename=export.md'}
                    )
                else:
                    return Response(
                        response.data,
                        mimetype='text/plain',
                        headers={'Content-Disposition': f'attachment; filename=export.{format_type}'}
                    )
            else:
                return self._format_response(response)

        @self.app.route('/api/statistics', methods=['GET'])
        def get_statistics_route():
            """Get database statistics"""
            response = self.get_statistics()
            return self._format_response(response)

        @self.app.route('/api/plugins', methods=['GET'])
        def list_plugins():
            """List available plugins"""
            importers = registry.list_importers()
            exporters = registry.list_exporters()

            return jsonify({
                "importers": [{"name": i.name, "description": i.description} for i in importers],
                "exporters": [{"name": e.name, "description": e.description} for e in exporters]
            })

    def _format_response(self, response: InterfaceResponse) -> Response:
        """Format InterfaceResponse for Flask"""
        status_code_map = {
            ResponseStatus.SUCCESS: 200,
            ResponseStatus.ERROR: 400,
            ResponseStatus.WARNING: 200,
            ResponseStatus.INFO: 200
        }

        return jsonify(response.to_dict()), status_code_map.get(response.status, 200)

    # Implement abstract methods from BaseInterface

    def import_conversations(
        self,
        source: Union[str, Dict, List],
        format: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs
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
                    return InterfaceResponse.error(f"No importer found for format: {format}")
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
                message=f"Successfully imported {len(conversations)} conversations"
            )
        except Exception as e:
            return self.handle_error(e)

    def export_conversations(
        self,
        output: Optional[str],
        format: str = "jsonl",
        conversation_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
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
                return InterfaceResponse.error(f"No exporter found for format: {format}")

            exported_data = exporter.export_conversations(conversations, output_file=output, **kwargs)

            return InterfaceResponse.success(
                data=exported_data,
                message=f"Successfully exported {len(conversations)} conversations"
            )
        except Exception as e:
            return self.handle_error(e)

    def search_conversations(
        self,
        query: str,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> InterfaceResponse:
        """Search conversations"""
        try:
            results = []
            if self.db:
                with self.db as db:
                    results = db.search_conversations(query, limit=limit)

            return InterfaceResponse.success(
                data=[r.to_dict() for r in results],
                message=f"Found {len(results)} conversations"
            )
        except Exception as e:
            return self.handle_error(e)

    def list_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
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
                        query = query.order_by(getattr(db.ConversationModel, sort_by).desc())

                    # Apply pagination
                    query = query.limit(limit).offset(offset)

                    for conv_model in query.all():
                        conversations.append(conv_model.to_dict())

            return InterfaceResponse.success(
                data={
                    "conversations": conversations,
                    "total": total,
                    "limit": limit,
                    "offset": offset
                }
            )
        except Exception as e:
            return self.handle_error(e)

    def get_conversation(
        self,
        conversation_id: str,
        include_paths: bool = False,
        **kwargs
    ) -> InterfaceResponse:
        """Get a specific conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv = db.load_conversation(conversation_id)

                if not conv:
                    return InterfaceResponse.error(f"Conversation {conversation_id} not found")

                data = {
                    "id": conv.id,
                    "title": conv.title,
                    "metadata": conv.metadata.to_dict(),
                    "message_count": len(conv.message_map)
                }

                if include_paths:
                    data["paths"] = []
                    for i, path in enumerate(conv.get_all_paths()):
                        data["paths"].append({
                            "path_id": i,
                            "length": len(path),
                            "messages": [m.to_dict() for m in path]
                        })
                else:
                    # Just include the longest path
                    data["messages"] = [m.to_dict() for m in conv.get_longest_path()]

            return InterfaceResponse.success(data=data)
        except Exception as e:
            return self.handle_error(e)

    def update_conversation(
        self,
        conversation_id: str,
        updates: Dict[str, Any],
        **kwargs
    ) -> InterfaceResponse:
        """Update conversation metadata"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                conv_model = db.session.query(db.ConversationModel).filter_by(id=conversation_id).first()

                if not conv_model:
                    return InterfaceResponse.error(f"Conversation {conversation_id} not found")

                # Update allowed fields
                if 'title' in updates:
                    conv_model.title = updates['title']
                if 'tags' in updates:
                    # Handle tag updates
                    pass
                if 'project' in updates:
                    conv_model.project = updates['project']

                db.session.commit()

            return InterfaceResponse.success(message=f"Conversation {conversation_id} updated")
        except Exception as e:
            return self.handle_error(e)

    def delete_conversation(
        self,
        conversation_id: str,
        **kwargs
    ) -> InterfaceResponse:
        """Delete a conversation"""
        try:
            if not self.db:
                return InterfaceResponse.error("Database not initialized")

            with self.db as db:
                db.delete_conversation(conversation_id)

            return InterfaceResponse.success(message=f"Conversation {conversation_id} deleted")
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