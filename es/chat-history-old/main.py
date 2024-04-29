from parse import parse_conversations  # Import your parsing function
from fastapi import FastAPI, Depends, HTTPException
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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(engine)

def convert_timestamp(timestamp):
    if timestamp is not None:
        return datetime.datetime.fromtimestamp(timestamp)
    return None

def import_data_to_db(file_path):
    # Create a new session
    session = Session()


    # Parse the conversations from the file
    parsed_conversations = parse_conversations(file_path)

    for conversation_data in parsed_conversations:
        # Create a new Conversation object
        conversation = Conversation(conversation_id=conversation_data['conversation_id'])
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
            session.add(message)

        session.commit()  # Commit the transaction

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create FastAPI App Instance
app = FastAPI()

# Define API Endpoints
@app.get("/conversations/")
def read_conversations(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    # Add logic to retrieve conversations from the database
    conversations = db.query(Conversation).offset(skip).limit(limit).all()
    return {"data": conversations}

@app.get("/conversations/{conversation_id}")
def read_conversation(conversation_id: str, db: Session = Depends(get_db)):
    # Add logic to retrieve a specific conversation from the database
    conversation = db.query(Conversation).filter(Conversation.conversation_id == conversation_id).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"data": conversation}

if __name__ == "__main__":
    import_data_to_db('data/conversations.json')
    # Run the application with uvicorn
    # uvicorn main:app --reload
    # Go to http://