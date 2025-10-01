#!/usr/bin/env python3
"""
Example REST API server for CTK

Usage:
    python examples/rest_server.py --db conversations.db --port 5000
"""

import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ctk.interfaces.rest import RestInterface


def main():
    parser = argparse.ArgumentParser(description="CTK REST API Server")
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    # Create and initialize the REST interface
    config = {
        "SECRET_KEY": "dev-secret-key-change-in-production",
        "MAX_CONTENT_LENGTH": 50 * 1024 * 1024  # 50MB max file upload
    }

    logger.info(f"Starting CTK REST API server...")
    logger.info(f"Database: {args.db}")
    logger.info(f"Server: http://{args.host}:{args.port}")

    try:
        # Create REST interface
        api = RestInterface(db_path=args.db, config=config)

        # Initialize
        response = api.initialize()
        if response.status != "success":
            logger.error(f"Failed to initialize API: {response.message}")
            sys.exit(1)

        logger.info("API initialized successfully")
        logger.info(f"Available endpoints:")
        logger.info(f"  GET    /api/health                   - Health check")
        logger.info(f"  GET    /api/conversations             - List conversations")
        logger.info(f"  GET    /api/conversations/<id>        - Get specific conversation")
        logger.info(f"  PATCH  /api/conversations/<id>        - Update conversation")
        logger.info(f"  DELETE /api/conversations/<id>        - Delete conversation")
        logger.info(f"  POST   /api/conversations/search      - Search conversations")
        logger.info(f"  POST   /api/import                    - Import conversations")
        logger.info(f"  POST   /api/export                    - Export conversations")
        logger.info(f"  GET    /api/statistics                - Get database statistics")
        logger.info(f"  GET    /api/plugins                   - List available plugins")

        # Run the server
        api.run(host=args.host, port=args.port, debug=args.debug)

    except KeyboardInterrupt:
        logger.info("\nShutting down server...")
        api.shutdown()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()