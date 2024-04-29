from parse import parse_conversations  # Import your parsing function
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session  # Import Session here
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
import datetime

# Define Database Models
Base = declarative_base()

class Conversation(Base):
    __tablename__ = 'conversations'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String, unique=True, index=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime)
    messages = relationship("Message", back_populates="conversation")

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True, index=True)
    conversation_id = Column(String, ForeignKey('conversations.conversation_id'))
    author = Column(String)
    timestamp = Column(DateTime)
    content = Column(String)
    conversation = relationship("Conversation", back_populates="messages")

# Database Connection and Session Creation
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat_history.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def convert_timestamp(timestamp):
    if timestamp is not None:
        return datetime.datetime.fromtimestamp(timestamp)
    return None

def import_data_to_db(file_path, num_conversations=2):
    # Create a new session
    session = SessionLocal()

    # Parse the conversations from the file
    parsed_conversations = parse_conversations(file_path)

    for conversation_data in parsed_conversations[:num_conversations]:
        # Create a new Conversation object
        conversation = Conversation(conversation_id=conversation_data['conversation_id'])
        print("Conversation:")
        session.add(conversation)
        session.flush()  # Flush to assign an ID to the conversation

        for message_data in conversation_data['messages']:
            # Convert timestamp
            timestamp = convert_timestamp(message_data['timestamp'])

            # Create a new Message object
            message = Message(
                message_id=message_data['message_id'],
                conversation_id=conversation.id,  # Link to the conversation
                author=message_data['author'],
                timestamp=timestamp,  # Use the converted timestamp
                content=message_data['content']
            )
            print("Message:")
            print(str(message))
            session.add(message)

        session.commit()  # Commit the transaction


# Clear the database
def clear_db():
    session = SessionLocal()
    session.query(Conversation).delete()
    session.query(Message).delete()
    session.commit()
    session.close()

# print contents of db
def print_db():
    session = SessionLocal()

    # Fetch and print all conversations
    conversations = session.query(Conversation).all()
    for conversation in conversations:
        print(f"Conversation ID: {conversation.conversation_id}, Start Time: {conversation.start_time}, End Time: {conversation.end_time}")
        
        # Fetch and print messages for each conversation
        messages = session.query(Message).filter_by(conversation_id=conversation.conversation_id).all()
        for message in messages:
            print(f"\tMessage ID: {message.message_id}, Author: {message.author}, Timestamp: {message.timestamp}, Content: {message.content}")

    session.close()

if __name__ == "__main__":
    clear_db()
    import_data_to_db('data/conversations.json')
    print_db()