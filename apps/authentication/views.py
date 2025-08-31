from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import login
from django.db.models import Q
from django.utils import timezone

from .models import User, UserSession, ClientInfo
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserListSerializer,
    ChangePasswordSerializer,
    UserSessionSerializer,
    ClientInfoSerializer
)
from .permissions import IsAdminUser


class UserRegistrationView(generics.CreateAPIView):
    """User registration endpoint."""
    
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'User registered successfully',
            'user': UserProfileSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    """User login endpoint with JWT token generation."""
    
    permission_classes = [permissions.AllowAny]
    
    def get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def post(self, request):
        serializer = UserLoginSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        login(request, user)
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # Create user session
        session = UserSession.objects.create(
            user=user,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Login successful',
            'user': UserProfileSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'session_id': session.id
        }, status=status.HTTP_200_OK)


class ClientInfoView(generics.RetrieveUpdateAPIView):
    """Client information view and update endpoint."""
    
    serializer_class = ClientInfoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Get or create client info for the current user."""
        client_info, created = ClientInfo.objects.get_or_create(
            user=self.request.user
        )
        return client_info
    
    def perform_update(self, serializer):
        """Mark client info as completed when updated."""
        serializer.save(is_completed=True)


class AdminClientInfoView(generics.RetrieveAPIView):
    """Admin-only endpoint to view client info for any user."""
    
    serializer_class = ClientInfoSerializer
    permission_classes = [IsAdminUser]
    
    def get_object(self):
        """Get client info for the specified user."""
        user_id = self.kwargs['user_id']
        try:
            user = User.objects.get(id=user_id)
            client_info = ClientInfo.objects.get(user=user)
            return client_info
        except (User.DoesNotExist, ClientInfo.DoesNotExist):
            return None
    
    def retrieve(self, request, *args, **kwargs):
        """Return client info or null if not found."""
        instance = self.get_object()
        if instance is None:
            return Response(None, status=status.HTTP_200_OK)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_client_info_status(request):
    """Check if user has completed client info form."""
    try:
        client_info = ClientInfo.objects.get(user=request.user)
        return Response({
            'has_client_info': True,
            'is_completed': client_info.is_completed
        }, status=status.HTTP_200_OK)
    except ClientInfo.DoesNotExist:
        return Response({
            'has_client_info': False,
            'is_completed': False
        }, status=status.HTTP_200_OK)


class UserLogoutView(APIView):
    """User logout endpoint."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            # End current session if session_id provided
            session_id = request.data.get('session_id')
            if session_id:
                try:
                    session = UserSession.objects.get(
                        id=session_id,
                        user=request.user,
                        session_end__isnull=True
                    )
                    session.end_session()
                except UserSession.DoesNotExist:
                    pass
            
            # Blacklist refresh token if provided
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Logout failed',
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile view and update endpoint."""
    
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """Change user password endpoint."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class UserListView(generics.ListAPIView):
    """Admin-only endpoint to list all users."""
    
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by subscription status
        subscription_status = self.request.query_params.get('subscription_status')
        if subscription_status:
            queryset = queryset.filter(subscription_status=subscription_status)
        
        # Filter by subscription type
        subscription_type = self.request.query_params.get('subscription_type')
        if subscription_type:
            queryset = queryset.filter(subscription_type=subscription_type)
        
        # Search by username, email, or name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        # Order by
        ordering = self.request.query_params.get('ordering', '-date_joined')
        if ordering:
            queryset = queryset.order_by(ordering)
        
        return queryset


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin-only endpoint to view, update, or delete specific users."""
    
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAdminUser]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return UserListSerializer
        return UserProfileSerializer
    
    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.is_admin:
            return Response({
                'error': 'Cannot delete admin users'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return super().destroy(request, *args, **kwargs)


class UserSessionListView(generics.ListAPIView):
    """List user sessions (admin can see all, users see their own)."""
    
    serializer_class = UserSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.is_admin:
            queryset = UserSession.objects.all()
            
            # Filter by user
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)
        else:
            queryset = UserSession.objects.filter(user=self.request.user)
        
        return queryset.order_by('-session_start')


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upgrade_user_subscription(request, user_id):
    """Admin endpoint to upgrade user subscription."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({
            'error': 'User not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    subscription_type = request.data.get('subscription_type')
    duration_days = request.data.get('duration_days')
    
    if not subscription_type:
        return Response({
            'error': 'subscription_type is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if subscription_type not in [choice[0] for choice in User.SubscriptionType.choices]:
        return Response({
            'error': 'Invalid subscription type'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user.upgrade_subscription(subscription_type, duration_days)
        return Response({
            'message': 'Subscription upgraded successfully',
            'user': UserProfileSerializer(user).data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Failed to upgrade subscription',
            'detail': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_stats(request):
    """Get current user's statistics."""
    user = request.user
    
    # Get user's sessions
    sessions = user.sessions.all()
    total_sessions = sessions.count()
    active_sessions = sessions.filter(session_end__isnull=True).count()
    
    # Calculate average session duration
    completed_sessions = sessions.filter(session_end__isnull=False)
    if completed_sessions.exists():
        total_duration = sum(
            (session.session_end - session.session_start).total_seconds()
            for session in completed_sessions
        )
        avg_session_duration = total_duration / completed_sessions.count()
    else:
        avg_session_duration = 0
    
    return Response({
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'avg_session_duration_seconds': avg_session_duration,
        'total_time_spent_seconds': user.total_time_spent.total_seconds(),
        'total_files': user.files.count(),
        'total_chat_messages': user.chat_messages.count(),
        'subscription_info': {
            'type': user.subscription_type,
            'status': user.subscription_status,
            'is_active': user.is_subscription_active,
            'days_until_expiry': user.days_until_expiry,
            'start_date': user.subscription_start_date,
            'end_date': user.subscription_end_date,
        }
    }, status=status.HTTP_200_OK)