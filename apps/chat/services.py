import time
import logging
import requests
import json
from typing import Dict, Any, Optional, Iterator
from django.conf import settings
from django.utils import timezone
from markdownify import markdownify as md
from .models import Conversation, ChatMessage, ChatTemplate, Folder

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI chat interactions (mock implementation)."""
    
    def __init__(self):
        self.model_name = "mock-ai-model-v1"
        self.max_tokens = 4000
        self.temperature = 0.7
    
    def generate_response(self, message: str, conversation_history: list = None) -> Dict[str, Any]:
        """Generate AI response to user message using external RAG API.
        
        Args:
            message: User's input message
            conversation_history: List of previous messages for context
            
        Returns:
            Dict containing response, tokens used, metadata, and sources
        """
        start_time = time.time()
        
        try:
            # Call external RAG API with conversation history
            rag_result = self._call_rag_api(message, conversation_history)
            
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Mock token calculation
            tokens_used = self._calculate_tokens(message, rag_result['response'])
            
            return {
                'response': rag_result['response'],
                'sources': rag_result['sources'],
                'tokens_used': tokens_used,
                'response_time_ms': response_time_ms,
                'model_used': 'rag-instant-ai',
                'success': True,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"AI service error: {str(e)}")
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'response': "I apologize, but I'm experiencing technical difficulties. Please try again later.",
                'tokens_used': 0,
                'response_time_ms': response_time_ms,
                'model_used': self.model_name,
                'success': False,
                'error': str(e)
            }
    
    def generate_response_stream(self, message: str, conversation_history: list = None) -> Iterator[Dict[str, Any]]:
        """Generate streaming AI response to user message using external RAG API.
        
        Args:
            message: User's input message
            conversation_history: List of previous messages for context
            
        Yields:
            Dict containing streaming response data
        """
        start_time = time.time()
        
        print("API ================== ")

        try:
            # Call external RAG API with conversation history (streaming)
            for chunk in self._call_rag_api_stream(message, conversation_history):
                # Calculate response time for each chunk
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Add metadata to each chunk
                chunk.update({
                    'response_time_ms': response_time_ms,
                    'model_used': 'rag-instant-ai',
                    'success': chunk.get('type') != 'error',
                    'error': chunk.get('error')
                })
                
                # Calculate tokens for complete responses
                if chunk.get('type') == 'success':
                    chunk['tokens_used'] = self._calculate_tokens(message, chunk.get('accumulated_response', ''))
                
                yield chunk
                
        except Exception as e:
            logger.error(f"AI service streaming error: {str(e)}")
            response_time_ms = int((time.time() - start_time) * 1000)
            
            yield {
                'type': 'error',
                'response': "I apologize, but I'm experiencing technical difficulties. Please try again later.",
                'sources': [],
                'tokens_used': 0,
                'response_time_ms': response_time_ms,
                'model_used': self.model_name,
                'success': False,
                'error': str(e)
            }
    
    def _call_rag_api(self, message: str, conversation_history: list = None) -> Dict[str, Any]:
        """Call external RAG API to get AI response and sources (non-streaming)."""
        try:
            url = "https://n8n.omadligrouphq.com/webhook/b1d1a7e1-d8e2-4fc8-ba74-486e5a07e757"
            headers = {
                "Content-Type": "application/json"
            }
            
            # Send only the current user message to webhook
            data = {"message": message}

            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Handle new webhook response format - array of objects
            if isinstance(result, list) and len(result) > 0:
                response_item = result[0]  # Get first item from array
                ai_response = response_item.get('content', '')
                
                # Extract document names from Document Names field
                sources = []
                if 'Document Names' in response_item:
                    document_names = response_item['Document Names']
                    if isinstance(document_names, list):
                        sources = document_names
            else:
                # Handle old format for backward compatibility
                ai_response = result.get('final_answer')
                source_document = result.get('source_document', '')
                sources = self._extract_sources_from_document(source_document)
            
            if not ai_response:
                logger.warning(f"No response found in RAG API result: {result}")
                return {
                    'response': "I apologize, but I couldn't generate a proper response. Please try again.",
                    'sources': []
                }
            
            # Convert HTML to Markdown for better frontend rendering
            markdown_response = md(ai_response, heading_style="ATX", bullets="-")
            
            return {
                'response': markdown_response,
                'sources': sources
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"RAG API request failed: {str(e)}")
            error_response = """## Apologies, but that question seems too general or outside my trained scope based on internal documents."""
            
            return {
                'response': error_response,
                'sources': []
            }
        except Exception as e:
            logger.error(f"RAG API processing error: {str(e)}")
            error_response = """## Apologies, but that question seems too general or outside my trained scope based on internal documents."""
            
            return {
                'response': error_response,
                'sources': []
            }
    
    def _call_rag_api_stream(self, message: str, conversation_history: list = None) -> Iterator[Dict[str, Any]]:
        """Call external RAG API to get streaming AI response and sources."""
        try:
            url = "https://n8n.omadligrouphq.com/webhook/b1d1a7e1-d8e2-4fc8-ba74-486e5a07e757"
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            }
            
            # Send only the current user message to webhook
            data = {"message": message}
            
            response = requests.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            
            # Handle new webhook response format - array of objects
            if isinstance(result, list) and len(result) > 0:
                response_item = result[0]  # Get first item from array
                
                # Extract content from the response
                if 'content' in response_item:
                    content = response_item['content']
                    
                    # Stream the content character by character or word by word
                    words = content.split(' ')
                    accumulated_text = ""
                    
                    for word in words:
                        accumulated_text += word + " "
                        yield {
                            'type': 'delta',
                            'content': word + " "
                        }
                    
                    # Extract document names from Document Names field
                    sources = []
                    if 'Document Names' in response_item:
                        document_names = response_item['Document Names']
                        if isinstance(document_names, list):
                            sources = document_names
                    
                    # Yield sources
                    if sources:
                        yield {
                            'type': 'source_document',
                            'source': sources
                        }
                    
                    # Convert HTML to Markdown for better frontend rendering
                    markdown_response = md(content, heading_style="ATX", bullets="-")
                    
                    # Final complete response
                    yield {
                        'type': 'complete',
                        'response': markdown_response,
                        'sources': sources,
                        'accumulated_response': content
                    }
                else:
                    # No content found
                    yield {
                        'type': 'error',
                        'error': 'No content found in webhook response'
                    }
            else:
                # Invalid response format
                yield {
                    'type': 'error',
                    'error': 'Invalid webhook response format'
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"RAG API streaming request failed: {str(e)}")
            yield {
                'type': 'error',
                'response': "I apologize, but I'm having trouble connecting to the knowledge base. Please try again later.",
                'sources': [],
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"RAG API streaming processing error: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            yield {
                'type': 'error',
                'response': "I apologize, but something went wrong while processing your request. Please try again.",
                'sources': [],
                'error': str(e)
            }
    
    def _format_conversation_for_api(self, current_message: str, conversation_history: list = None) -> list:
        """Format conversation history for the RAG API according to the required structure.
        
        Args:
            current_message: The current user message
            conversation_history: List of previous messages with 'role' and 'content' keys
            
        Returns:
            List formatted for the API with message_type and content
        """
        if not conversation_history:
            # First question - only current message
            return [{
                "message_type": "user",
                "content": current_message
            }]
        
        # Build the conversation history in reverse chronological order
        formatted_messages = []
        
        # Add current message first
        formatted_messages.append({
            "message_type": "user",
            "content": current_message
        })
        
        # Add previous messages in reverse order (most recent first, excluding current)
        # Skip the last message if it's the current user message
        history_to_process = conversation_history[:-1] if conversation_history else []
        
        for message in reversed(history_to_process):
            message_type = "user" if message.get('role') == 'user' else "assistant"
            formatted_messages.append({
                "message_type": message_type,
                "content": message.get('content', '')
            })
        
        return formatted_messages
    
    def _extract_sources_from_document(self, source_document: str) -> list:
        """Extract document names from source_document string.
        
        Args:
            source_document: String like "Sources: Meeting Rhythms & GSRs.docx, Q3 Strategy Planning _ Mid-Year Review Guide.docx"
            
        Returns:
            List of document names: ["Meeting Rhythms & GSRs.docx", "Q3 Strategy Planning _ Mid-Year Review Guide.docx"]
        """
        if not source_document:
            return []
        
        try:
            # Remove "Sources: " prefix if present
            if source_document.startswith("Sources: "):
                source_document = source_document[9:]  # Remove "Sources: "
            
            # Split by comma and clean up each document name
            documents = [doc.strip() for doc in source_document.split(',')]
            
            # Filter out empty strings
            documents = [doc for doc in documents if doc]
            
            return documents
            
        except Exception as e:
            logger.error(f"Error extracting sources from document: {str(e)}")
            return []
    
    def _calculate_tokens(self, input_text: str, output_text: str) -> int:
        """Mock token calculation (roughly 4 characters per token)."""
        total_chars = len(input_text) + len(output_text)
        return max(1, total_chars // 4)


class ChatService:
    """Service for managing chat conversations and messages."""
    
    def __init__(self):
        self.ai_service = AIService()
    
    def process_chat_message(
        self,
        user,
        message_content: str,
        conversation_id: Optional[str] = None,
        template_id: Optional[int] = None,
        folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a chat message and generate AI response.
        
        Args:
            user: User instance
            message_content: User's message content
            conversation_id: Optional existing conversation ID
            template_id: Optional template ID to use
            
        Returns:
            Dict containing conversation and message data
        """
        try:
            # Get or create conversation
            if conversation_id:
                conversation = Conversation.objects.get(
                    id=conversation_id,
                    user=user
                )
            else:
                # Create new conversation with optional folder assignment
                conversation_data = {'user': user}
                if folder_id:
                    try:
                        folder = Folder.objects.get(id=folder_id, user=user)
                        conversation_data['folder'] = folder
                    except Folder.DoesNotExist:
                        # If folder doesn't exist or doesn't belong to user, create without folder
                        pass
                conversation = Conversation.objects.create(**conversation_data)
            
            # Apply template if specified
            if template_id:
                template = ChatTemplate.objects.get(
                    id=template_id,
                    is_public=True
                )
                message_content = f"{template.prompt}\n\n{message_content}"
                template.increment_usage()
            
            # Create user message
            user_message = ChatMessage.objects.create(
                conversation=conversation,
                user=user,
                message_type=ChatMessage.MessageType.USER,
                content=message_content,
                status=ChatMessage.MessageStatus.COMPLETED
            )
            
            # Get conversation history for context
            conversation_history = self._get_conversation_history(conversation)
            
            # Generate AI response
            ai_result = self.ai_service.generate_response(
                message_content,
                conversation_history
            )
            
            # Create assistant message
            assistant_message = ChatMessage.objects.create(
                conversation=conversation,
                user=user,
                message_type=ChatMessage.MessageType.ASSISTANT,
                content=ai_result['response'],
                sources=ai_result.get('sources', []),
                status=ChatMessage.MessageStatus.COMPLETED if ai_result['success'] else ChatMessage.MessageStatus.FAILED,
                tokens_used=ai_result['tokens_used'],
                model_used=ai_result['model_used'],
                response_time_ms=ai_result['response_time_ms'],
                error_message=ai_result['error'] or ''
            )
            
            # Update conversation stats
            conversation.update_stats()
            
            # Update user session activity
            self._update_user_activity(user)
            
            return {
                'success': True,
                'conversation_id': conversation.id,
                'user_message': user_message,
                'assistant_message': assistant_message,
                'tokens_used': ai_result['tokens_used'],
                'response_time_ms': ai_result['response_time_ms']
            }
            
        except Exception as e:
            logger.error(f"Chat service error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def process_chat_message_stream(
        self,
        user,
        message_content: str,
        conversation_id: Optional[str] = None,
        template_id: Optional[int] = None,
        folder_id: Optional[str] = None
    ) -> Iterator[Dict[str, Any]]:
        """Process a chat message and generate streaming AI response.
        
        Args:
            user: User instance
            message_content: User's message content
            conversation_id: Optional existing conversation ID
            template_id: Optional template ID to use
            
        Yields:
            Dict containing streaming response data
        """
        try:
            # Get or create conversation
            if conversation_id:
                conversation = Conversation.objects.get(
                    id=conversation_id,
                    user=user
                )
            else:
                # Create new conversation with optional folder assignment
                conversation_data = {'user': user}
                if folder_id:
                    try:
                        folder = Folder.objects.get(id=folder_id, user=user)
                        conversation_data['folder'] = folder
                    except Folder.DoesNotExist:
                        # If folder doesn't exist or doesn't belong to user, create without folder
                        pass
                conversation = Conversation.objects.create(**conversation_data)
            
            # Apply template if specified
            if template_id:
                template = ChatTemplate.objects.get(
                    id=template_id,
                    is_public=True
                )
                message_content = f"{template.prompt}\n\n{message_content}"
                template.increment_usage()
            
            # Create user message
            user_message = ChatMessage.objects.create(
                conversation=conversation,
                user=user,
                message_type=ChatMessage.MessageType.USER,
                content=message_content,
                status=ChatMessage.MessageStatus.COMPLETED
            )
            
            # Get conversation history for context
            conversation_history = self._get_conversation_history(conversation)
            
            # Create assistant message placeholder
            assistant_message = ChatMessage.objects.create(
                conversation=conversation,
                user=user,
                message_type=ChatMessage.MessageType.ASSISTANT,
                content="",
                status=ChatMessage.MessageStatus.PROCESSING
            )
            
            accumulated_response = ""
            sources = []
            
            # Stream AI response
            for chunk in self.ai_service.generate_response_stream(message_content, conversation_history):
                # Update accumulated response for delta chunks
                if chunk.get('type') == 'delta':
                    accumulated_response = chunk.get('accumulated_response', '')
                    assistant_message.content = accumulated_response
                    assistant_message.save(update_fields=['content'])
                    
                elif chunk.get('type') == 'sources':
                    sources = chunk.get('sources', [])
                    assistant_message.sources = sources
                    assistant_message.save(update_fields=['sources'])
                    
                elif chunk.get('type') == 'complete':
                    accumulated_response = chunk.get('response', '')
                    sources = chunk.get('sources', [])
                    assistant_message.content = accumulated_response
                    assistant_message.sources = sources
                    assistant_message.status = ChatMessage.MessageStatus.COMPLETED
                    assistant_message.tokens_used = chunk.get('tokens_used', 0)
                    assistant_message.model_used = chunk.get('model_used', '')
                    assistant_message.response_time_ms = chunk.get('response_time_ms', 0)
                    assistant_message.save()
                    
                    # Update conversation stats
                    conversation.update_stats()
                    
                    # Update user session activity
                    self._update_user_activity(user)
                    
                elif chunk.get('type') == 'error':
                    assistant_message.content = chunk.get('response', 'An error occurred')
                    assistant_message.status = ChatMessage.MessageStatus.FAILED
                    assistant_message.error_message = chunk.get('error', '')
                    assistant_message.save()
                
                # Yield chunk with message and conversation info
                chunk_response = {
                    **chunk,
                    'conversation_id': str(conversation.id),
                    'user_message_id': str(user_message.id),
                    'assistant_message_id': str(assistant_message.id)
                }
                
                yield chunk_response
                
        except Exception as e:
            yield {
                'type': 'error',
                'response': 'An error occurred while processing your message.',
                'sources': [],
                'error': str(e),
                 'success': False
             }
    
    def _get_conversation_history(self, conversation: Conversation, limit: int = 10) -> list:
        """Get recent conversation history for context."""
        messages = conversation.messages.order_by('-created_at')[:limit]
        history = []
        
        for message in reversed(messages):
            history.append({
                'role': 'user' if message.is_from_user else 'assistant',
                'content': message.content,
                'timestamp': message.created_at.isoformat()
            })
        
        return history
    
    def _update_user_activity(self, user):
        """Update user's last activity and session info."""
        user.last_activity = timezone.now()
        user.save(update_fields=['last_activity'])
        
        # Update current session if exists
        current_session = user.sessions.filter(
            session_end__isnull=True
        ).first()
        
        if current_session:
            current_session.chat_messages_sent += 1
            current_session.save(update_fields=['chat_messages_sent'])
    
    def get_conversation_stats(self, user) -> Dict[str, Any]:
        """Get conversation statistics for user."""
        conversations = user.conversations.all()
        messages = ChatMessage.objects.filter(user=user)
        
        total_conversations = conversations.count()
        total_messages = messages.count()
        total_tokens = sum(msg.tokens_used or 0 for msg in messages)
        
        # Calculate averages
        avg_messages_per_conversation = (
            total_messages / total_conversations if total_conversations > 0 else 0
        )
        
        # Calculate average response time
        assistant_messages = messages.filter(
            message_type=ChatMessage.MessageType.ASSISTANT,
            response_time_ms__isnull=False
        )
        
        if assistant_messages.exists():
            avg_response_time = sum(
                msg.response_time_ms for msg in assistant_messages
            ) / assistant_messages.count()
        else:
            avg_response_time = 0
        
        # Get time-based stats
        now = timezone.now()
        week_ago = now - timezone.timedelta(days=7)
        month_ago = now - timezone.timedelta(days=30)
        
        conversations_this_week = conversations.filter(
            created_at__gte=week_ago
        ).count()
        
        conversations_this_month = conversations.filter(
            created_at__gte=month_ago
        ).count()
        
        # Find most active day
        most_active_day = "No data"
        if conversations.exists():
            # Simple implementation - could be more sophisticated
            most_active_day = conversations.first().created_at.strftime('%A')
        
        return {
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'total_tokens_used': total_tokens,
            'avg_messages_per_conversation': round(avg_messages_per_conversation, 2),
            'avg_response_time_ms': round(avg_response_time, 2),
            'most_active_day': most_active_day,
            'conversations_this_week': conversations_this_week,
            'conversations_this_month': conversations_this_month
        }
    
    def archive_conversation(self, user, conversation_id: str) -> bool:
        """Archive a conversation."""
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                user=user
            )
            conversation.is_archived = True
            conversation.save(update_fields=['is_archived'])
            return True
        except Conversation.DoesNotExist:
            return False
    
    def delete_conversation(self, user, conversation_id: str) -> bool:
        """Delete a conversation and all its messages."""
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                user=user
            )
            conversation.delete()
            return True
        except Conversation.DoesNotExist:
            return False
    
    def export_conversation(self, user, conversation_id: str) -> Dict[str, Any]:
        """Export conversation data."""
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                user=user
            )
            
            messages_data = []
            for message in conversation.messages.all():
                messages_data.append({
                    'timestamp': message.created_at.isoformat(),
                    'type': message.message_type,
                    'content': message.content,
                    'tokens_used': message.tokens_used,
                    'response_time_ms': message.response_time_ms
                })
            
            return {
                'conversation_id': str(conversation.id),
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat(),
                'total_messages': conversation.total_messages,
                'total_tokens_used': conversation.total_tokens_used,
                'messages': messages_data
            }
            
        except Conversation.DoesNotExist:
            return None


class FeedbackService:
    """Service for handling feedback interactions with RAG API."""
    
    def __init__(self):
        self.rag_base_url = "https://n8n.omadligrouphq.com"
    
    def submit_thumbs_feedback(self, question: str, answer: str, feedback_type: str, comment: str = None) -> Dict[str, Any]:
        """Submit thumbs up/down feedback to RAG API.
        
        Args:
            question: The user's original question
            answer: The AI's response that was rated
            feedback_type: 'thumbs_up' or 'thumbs_down'
            comment: Optional comment for thumbs down feedback
            
        Returns:
            Dict containing success status and response data
        """
        start_time = time.time()
        
        try:
            # Prepare feedback data for RAG API
            feedback_data = {
                "question": question,
                "answer": answer,
                "feedback_type": feedback_type,
                "timestamp": timezone.now().isoformat()
            }
            
            # Add comment for thumbs down feedback
            if feedback_type == "thumbs_down" and comment:
                feedback_data["comment"] = comment
                self.get_feedbacks_by_status(False)
            elif feedback_type == "thumbs_up":
                feedback_data["comment"] = "thumb up"
                self.get_feedbacks_by_status(True)
            
            # Call RAG API feedback endpoint
            response = self._call_rag_feedback_api(feedback_data)
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'success': True,
                'response': response,
                'response_time_ms': response_time_ms,
                'feedback_type': feedback_type,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Feedback service error: {str(e)}")
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'success': False,
                'response': None,
                'response_time_ms': response_time_ms,
                'feedback_type': feedback_type,
                'error': str(e)
            }
    
    def _call_rag_feedback_api(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Call RAG API feedback endpoint (legacy support only)."""
        try:
            # Only send to original RAG API for backward compatibility
            # Webhook is now handled in FeedbackView to avoid duplication
            url = f"{self.rag_base_url}/feedback/"
            response = requests.post(
                url,
                json=feedback_data,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Feedback submitted successfully to RAG API")
                return response.json()
            else:
                logger.error(f"Failed to submit feedback to RAG API: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling RAG feedback API: {str(e)}")
            return None
    

    
    def get_feedback_analytics(self, date_from: str = None, date_to: str = None) -> Dict[str, Any]:
        """Get feedback analytics from RAG API.
        
        Args:
            date_from: Start date for analytics (ISO format)
            date_to: End date for analytics (ISO format)
            
        Returns:
            Dict containing feedback analytics data
        """
        try:
            url = "https://n8n.omadligrouphq.com/webhook/8ab1aff6-af35-4fd3-8098-eceedfc97ac0"
            params = {}
            
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            return {
                'success': True,
                'data': result,
                'error': None
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"RAG API analytics request failed: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': f"Failed to get analytics from RAG service: {str(e)}"
            }
        except Exception as e:
            logger.error(f"RAG API analytics processing error: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': f"Error processing analytics request: {str(e)}"
            }
    
    def get_feedbacks_by_status(self, status: bool = None, date_from: str = None, date_to: str = None) -> Dict[str, Any]:
        """Get feedbacks filtered by status from RAG API.
        
        Args:
            status: True for thumbs_up, False for thumbs_down, None for all
            date_from: Start date for filtering (ISO format)
            date_to: End date for filtering (ISO format)
            
        Returns:
            Dict containing filtered feedbacks data
        """
        try:
            url = "https://n8n.omadligrouphq.com/webhook/8ab1aff6-af35-4fd3-8098-eceedfc97ac0"
            params = {}
            
            if status is not None:
                params['status'] = 'true' if status else 'false'
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            return {
                'success': True,
                'data': result,
                'error': None
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"RAG API feedbacks request failed: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': f"Failed to get feedbacks from RAG service: {str(e)}"
            }
        except Exception as e:
            logger.error(f"RAG API feedbacks processing error: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': f"Error processing feedbacks request: {str(e)}"
            }