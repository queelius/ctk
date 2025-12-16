"""
Chat and LLM command handlers

Implements: chat, say
"""

from typing import List, Dict, Callable
from ctk.core.command_dispatcher import CommandResult


class ChatCommands:
    """Handler for chat-related commands"""

    def __init__(self, tui_instance=None):
        """
        Initialize chat command handlers

        Args:
            tui_instance: TUI instance for mode switching and chat
        """
        self.tui = tui_instance

        if not tui_instance:
            raise ValueError("ChatCommands requires tui_instance for mode switching")

    def cmd_chat(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Enter chat mode or send a message

        Usage:
            chat                    - Enter interactive chat mode
            chat <message>          - Send message and enter chat mode
            echo "text" | chat      - Send piped text as message

        Args:
            args: Command arguments (message text)
            stdin: Standard input (piped message)

        Returns:
            CommandResult with success status
        """
        # Get message from args or stdin
        if stdin:
            message = stdin.strip()
        elif args:
            message = ' '.join(args)
        else:
            message = None

        # Load conversation from current VFS path if in a conversation
        from ctk.core.vfs import VFSPathParser, PathType
        current_vfs_path = self.tui.vfs_cwd

        try:
            parsed_path = VFSPathParser.parse(current_vfs_path)

            # Check if we're in a conversation or message node
            if parsed_path.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                conv_id = parsed_path.conversation_id
                message_path = parsed_path.message_path if parsed_path.message_path else []

                # Load conversation from database
                if self.tui.db:
                    conversation = self.tui.db.load_conversation(conv_id)
                    if conversation:
                        # Load into TUI tree structure
                        self.tui.load_conversation_tree(conversation)
                        self.tui.current_conversation_id = conv_id

                        # Navigate to the specific message node
                        if message_path:
                            # Navigate to the message specified in the path
                            # First segment (m1) selects the root message
                            # Subsequent segments navigate through children
                            current_msg = None

                            for i, node_name in enumerate(message_path):
                                # Extract index from node name (m1 -> 1, m2 -> 2)
                                if not node_name.lower().startswith('m'):
                                    break

                                try:
                                    node_index = int(node_name[1:]) - 1  # m1 -> 0, m2 -> 1
                                except ValueError:
                                    break

                                if i == 0:
                                    # First segment: select from root messages
                                    # For now, assume single root (self.tui.root)
                                    # TODO: Handle multiple root messages
                                    if node_index == 0 and self.tui.root:
                                        current_msg = self.tui.root
                                    else:
                                        break
                                else:
                                    # Subsequent segments: navigate through children
                                    if current_msg and len(current_msg.children) > node_index:
                                        current_msg = current_msg.children[node_index]
                                    else:
                                        break

                            # Set current message to the navigated node
                            if current_msg:
                                self.tui.current_message = current_msg
                        # Note: if at conversation root (no message_path),
                        # load_conversation_tree() already set current_message to most recent leaf
        except Exception as e:
            # If path parsing fails, just continue with empty conversation
            pass

        # Switch to chat mode
        self.tui.mode = 'chat'

        # If message provided, send it immediately
        if message:
            # Send message to chat
            self.tui.chat(message)

        return CommandResult(
            success=True,
            output="Entering chat mode. Type /exit to return to shell.\n"
        )

    def cmd_say(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Send a message to the LLM without entering chat mode

        Usage:
            say <message>           - Send message and get response
            say hello               - Greet the LLM
            echo "text" | say       - Send piped text as message

        This is the explicit way to talk to the LLM from shell mode.
        The conversation context and CTK tools are available.

        Args:
            args: Command arguments (message text)
            stdin: Standard input (piped message)

        Returns:
            CommandResult with success status (output is printed by chat())
        """
        # Get message from args or stdin
        if stdin:
            message = stdin.strip()
        elif args:
            message = ' '.join(args)
        else:
            return CommandResult(
                success=False,
                output="",
                error="say: no message provided. Usage: say <message>"
            )

        # Send message using the TUI chat method (handles tools, context, etc.)
        try:
            self.tui.chat(message)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"say: error: {str(e)}"
            )


def create_chat_commands(tui_instance=None) -> Dict[str, Callable]:
    """
    Create chat command handlers

    Args:
        tui_instance: TUI instance for mode switching

    Returns:
        Dictionary mapping command names to handlers
    """
    chat_cmds = ChatCommands(tui_instance)

    return {
        'chat': chat_cmds.cmd_chat,
        'say': chat_cmds.cmd_say,
    }
