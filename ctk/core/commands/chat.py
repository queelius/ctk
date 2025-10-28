"""
Chat and LLM command handlers

Implements: chat, complete
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
                            current_msg = self.tui.root

                            for node_name in message_path:
                                # Extract index from node name (m1 -> 1, m2 -> 2)
                                if not node_name.lower().startswith('m'):
                                    break

                                try:
                                    node_index = int(node_name[1:])  # Remove 'm' prefix
                                except ValueError:
                                    break

                                # Get children
                                if current_msg and len(current_msg.children) >= node_index:
                                    current_msg = current_msg.children[node_index - 1]
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

    def cmd_complete(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Get LLM completion without entering chat mode

        Usage:
            complete <prompt>           - Get completion for prompt
            echo "prompt" | complete    - Get completion from stdin

        Args:
            args: Command arguments (prompt text)
            stdin: Standard input (piped prompt)

        Returns:
            CommandResult with LLM response
        """
        # Get prompt from args or stdin
        if stdin:
            prompt = stdin.strip()
        elif args:
            prompt = ' '.join(args)
        else:
            return CommandResult(
                success=False,
                output="",
                error="complete: no prompt provided"
            )

        # Get completion without switching modes
        if not self.tui.provider:
            return CommandResult(
                success=False,
                output="",
                error="complete: No LLM provider configured"
            )

        try:
            # Get streaming response
            response_text = ""
            for chunk in self.tui.provider.chat([
                {"role": "user", "content": prompt}
            ], stream=True):
                if isinstance(chunk, dict) and 'content' in chunk:
                    response_text += chunk['content']
                elif isinstance(chunk, str):
                    response_text += chunk

            return CommandResult(
                success=True,
                output=response_text + "\n"
            )

        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"complete: LLM error: {str(e)}"
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
        'complete': chat_cmds.cmd_complete,
    }
