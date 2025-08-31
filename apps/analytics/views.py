from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from django.http import HttpResponse, Http404
from datetime import datetime, timedelta, date
from typing import Dict, Any
import json

from .models import (
    AnalyticsEvent, UserActivity, SystemMetrics, Report,
    FeatureUsage, ErrorLog, PaymentRecord
)
from .serializers import (
    AnalyticsEventSerializer, CreateEventSerializer, UserActivitySerializer,
    SystemMetricsSerializer, ReportSerializer, CreateReportSerializer,
    FeatureUsageSerializer, ErrorLogSerializer, DashboardStatsSerializer,
    AnalyticsFilterSerializer
)
from .services import AnalyticsService, ReportService, ErrorTrackingService
from apps.authentication.permissions import IsAdminUser, IsActiveSubscription

User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AnalyticsEventListView(generics.ListCreateAPIView):
    """List and create analytics events"""
    serializer_class = AnalyticsEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = AnalyticsEvent.objects.all()
        
        # Filter by user if not admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        
        # Apply filters
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        start_date = self.request.query_params.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__gte=start_date)
            except ValueError:
                pass
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__lte=end_date)
            except ValueError:
                pass
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(event_name__icontains=search) |
                Q(event_description__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateEventSerializer
        return AnalyticsEventSerializer
    
    def perform_create(self, serializer):
        # Get request metadata
        request = self.request
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        referer = request.META.get('HTTP_REFERER', '')
        session_id = request.session.session_key
        
        # Track the event
        AnalyticsService.track_event(
            event_type=serializer.validated_data['event_type'],
            event_name=serializer.validated_data['event_name'],
            event_description=serializer.validated_data.get('event_description', ''),
            user=request.user,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            properties=serializer.validated_data.get('properties', {}),
            metadata=serializer.validated_data.get('metadata', {})
        )


class UserActivityListView(generics.ListAPIView):
    """List user activity"""
    serializer_class = UserActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = UserActivity.objects.all()
        
        # Filter by user if not admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        
        # Apply filters
        user_id = self.request.query_params.get('user_id')
        if user_id and self.request.user.is_staff:
            queryset = queryset.filter(user_id=user_id)
        
        start_date = self.request.query_params.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                pass
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                pass
        
        return queryset.order_by('-date')


class SystemMetricsListView(generics.ListAPIView):
    """List system metrics (admin only)"""
    serializer_class = SystemMetricsSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = SystemMetrics.objects.all()
        
        # Apply filters
        start_date = self.request.query_params.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                pass
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                pass
        
        return queryset.order_by('-date')


class ReportListCreateView(generics.ListCreateAPIView):
    """List and create reports"""
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveSubscription]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = Report.objects.all()
        
        # Filter by user if not admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(requested_by=self.request.user)
        
        # Apply filters
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateReportSerializer
        return ReportSerializer
    
    def perform_create(self, serializer):
        ReportService.create_report(
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', ''),
            report_type=serializer.validated_data['report_type'],
            report_format=serializer.validated_data['report_format'],
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data['end_date'],
            filters=serializer.validated_data.get('filters', {}),
            parameters=serializer.validated_data.get('parameters', {}),
            user=self.request.user
        )


class ReportDetailView(generics.RetrieveAPIView):
    """Retrieve report details"""
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Report.objects.none()
        queryset = Report.objects.all()
        
        # Filter by user if not admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(requested_by=self.request.user)
        
        return queryset


class ReportDownloadView(generics.RetrieveAPIView):
    """Download report file"""
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Report.objects.none()
        queryset = Report.objects.filter(status='completed')
        
        # Filter by user if not admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(requested_by=self.request.user)
        
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        report = self.get_object()
        
        if not report.file_path or report.status != 'completed':
            raise Http404("Report file not found or not ready")
        
        # In a real app, serve file from storage service
        # For now, return the data as JSON or CSV
        if report.report_format == 'json':
            response = HttpResponse(
                json.dumps(report.data, indent=2, default=str),
                content_type='application/json'
            )
            response['Content-Disposition'] = f'attachment; filename="{report.name}.json"'
        elif report.report_format == 'csv':
            from .services import ReportService
            csv_content = ReportService._convert_to_csv(report.data)
            response = HttpResponse(csv_content, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{report.name}.csv"'
        else:
            raise Http404("Unsupported report format")
        
        return response


class FeatureUsageListView(generics.ListAPIView):
    """List feature usage statistics"""
    serializer_class = FeatureUsageSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = FeatureUsage.objects.all()
        
        # Apply filters
        feature_name = self.request.query_params.get('feature_name')
        if feature_name:
            queryset = queryset.filter(feature_name__icontains=feature_name)
        
        start_date = self.request.query_params.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                pass
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                pass
        
        return queryset.order_by('-date', '-total_uses')


class ErrorLogListView(generics.ListAPIView):
    """List error logs (admin only)"""
    serializer_class = ErrorLogSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = ErrorLog.objects.all()
        
        # Apply filters
        level = self.request.query_params.get('level')
        if level:
            queryset = queryset.filter(level=level)
        
        is_resolved = self.request.query_params.get('is_resolved')
        if is_resolved is not None:
            queryset = queryset.filter(is_resolved=is_resolved.lower() == 'true')
        
        exception_type = self.request.query_params.get('exception_type')
        if exception_type:
            queryset = queryset.filter(exception_type__icontains=exception_type)
        
        start_date = self.request.query_params.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                queryset = queryset.filter(created_at__lte=end_date)
            except ValueError:
                pass
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(message__icontains=search) |
                Q(exception_type__icontains=search) |
                Q(url__icontains=search)
            )
        
        return queryset.order_by('-created_at')


class ErrorLogDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve and update error log (admin only)"""
    queryset = ErrorLog.objects.all()
    serializer_class = ErrorLogSerializer
    permission_classes = [IsAdminUser]
    
    def perform_update(self, serializer):
        error_log = serializer.save()
        
        # If marking as resolved, set resolved_by and resolved_at
        if serializer.validated_data.get('is_resolved') and not error_log.resolved_at:
            error_log.resolved_by = self.request.user
            error_log.resolved_at = timezone.now()
            error_log.save()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Get dashboard statistics"""
    try:
        # Get date range from query params
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Default to last 7 days if no dates provided
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=7)
        if not end_date:
            end_date = timezone.now().date()
        
        # Get dashboard statistics
        stats = AnalyticsService.get_dashboard_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response(stats, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to get dashboard stats: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def subscription_stats(request):
    """Get subscription statistics (Admin only)"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        stats = AnalyticsService.get_subscription_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response(stats, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to get subscription stats: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def payment_stats(request):
    """Get payment statistics (Admin only)"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        stats = AnalyticsService.get_payment_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response(stats, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to get payment stats: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_dashboard_stats(request):
    """Get user-specific dashboard statistics"""
    try:
        # Admin can view any user's stats, regular users can only view their own
        user_id = request.GET.get('user_id')
        
        if user_id and not request.user.is_admin:
            return Response(
                {'error': 'Permission denied. Only admins can view other users\' stats.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # If no user_id provided or user is not admin, use current user
        if not user_id or not request.user.is_admin:
            user_id = request.user.id
        
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        stats = AnalyticsService.get_user_dashboard_stats(
            user_id=int(user_id),
            start_date=start_date,
            end_date=end_date
        )
        
        return Response(stats, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to get user dashboard stats: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def users_list_stats(request):
    """Get users list with subscription and activity stats (Admin only)"""
    try:
        from apps.authentication.models import User
        
        # Get query parameters
        search = request.GET.get('search', '')
        subscription_type = request.GET.get('subscription_type')
        subscription_status = request.GET.get('subscription_status')
        role = request.GET.get('role')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # Build queryset
        queryset = User.objects.all().order_by('-date_joined')
        
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        if subscription_type:
            queryset = queryset.filter(subscription_type=subscription_type)
        
        if subscription_status:
            queryset = queryset.filter(subscription_status=subscription_status)
        
        if role:
            queryset = queryset.filter(role=role)
        
        # Pagination
        total_count = queryset.count()
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        users = queryset[start_index:end_index]
        
        # Prepare user data with stats
        users_data = []
        for user in users:
            # Get user's payment history
            payment_history = PaymentRecord.objects.filter(
                user=user, status='completed'
            ).order_by('-created_at')[:5]
            
            # Get user's recent activity
            recent_activity = UserActivity.objects.filter(
                user=user
            ).order_by('-date')[:7]
            
            # Calculate total time spent
            total_time = sum(
                activity.total_session_time for activity in recent_activity
            )
            
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.get_full_name(),
                'subscription_type': getattr(user, 'subscription_type', None),
                'subscription_status': getattr(user, 'subscription_status', None),
                'subscription_start_date': getattr(user, 'subscription_start_date', None),
                'subscription_end_date': getattr(user, 'subscription_end_date', None),
                'date_joined': user.date_joined,
                'last_login': user.last_login,
                'total_time_spent': total_time,
                'payment_history': [
                    {
                        'amount': payment.amount,
                        'currency': payment.currency,
                        'payment_type': payment.payment_type,
                        'created_at': payment.created_at
                    } for payment in payment_history
                ],
                'recent_activity': [
                    {
                        'date': activity.date,
                        'login_count': activity.login_count,
                        'chat_messages_sent': activity.chat_messages_sent,
                        'files_uploaded': activity.files_uploaded,
                        'total_session_time': activity.total_session_time
                    } for activity in recent_activity
                ]
            })
        
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': users_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to get users list: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_activity_stats(request):
    """Get user activity statistics"""
    # Get filters from query params
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    user_id = request.query_params.get('user_id')
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            end_date = None
    
    # Only allow user_id filter for admin users
    if not request.user.is_staff:
        user_id = request.user.id
    elif user_id:
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = None
    
    # Get stats
    stats = AnalyticsService.get_user_activity_stats(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return Response(stats)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def error_stats(request):
    """Get error statistics (admin only)"""
    # Get date range from query params
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            end_date = None
    
    # Get stats
    stats = ErrorTrackingService.get_error_stats(start_date, end_date)
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def track_event(request):
    """Track a custom analytics event"""
    serializer = CreateEventSerializer(data=request.data)
    
    if serializer.is_valid():
        # Get request metadata
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        referer = request.META.get('HTTP_REFERER', '')
        session_id = request.session.session_key
        
        # Track the event
        event = AnalyticsService.track_event(
            event_type=serializer.validated_data['event_type'],
            event_name=serializer.validated_data['event_name'],
            event_description=serializer.validated_data.get('event_description', ''),
            user=request.user,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            properties=serializer.validated_data.get('properties', {}),
            metadata=serializer.validated_data.get('metadata', {})
        )
        
        return Response(
            AnalyticsEventSerializer(event).data,
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def log_error(request):
    """Log an error (admin only)"""
    data = request.data
    
    # Get request metadata
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Log the error
    error_log = ErrorTrackingService.log_error(
        level=data.get('level', 'error'),
        message=data.get('message', ''),
        exception_type=data.get('exception_type'),
        stack_trace=data.get('stack_trace'),
        url=data.get('url'),
        method=data.get('method'),
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent,
        context=data.get('context', {})
    )
    
    return Response(
        ErrorLogSerializer(error_log).data,
        status=status.HTTP_201_CREATED
    )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_health(request):
    """Get system health metrics (admin only)"""
    today = timezone.now().date()
    
    # Get latest system metrics
    latest_metrics = SystemMetrics.objects.filter(
        date__lte=today
    ).order_by('-date').first()
    
    if not latest_metrics:
        # Create metrics for today if none exist
        latest_metrics = AnalyticsService.get_system_metrics(today)
    
    # Get recent error rate
    recent_errors = ErrorLog.objects.filter(
        created_at__date__gte=today - timedelta(days=7)
    ).count()
    
    recent_events = AnalyticsEvent.objects.filter(
        created_at__date__gte=today - timedelta(days=7)
    ).count()
    
    error_rate = (recent_errors / recent_events * 100) if recent_events > 0 else 0
    
    health_data = {
        'status': 'healthy' if error_rate < 5 else 'warning' if error_rate < 10 else 'critical',
        'uptime_percentage': latest_metrics.uptime_percentage,
        'avg_response_time': latest_metrics.avg_response_time,
        'error_rate': error_rate,
        'total_users': latest_metrics.total_users,
        'active_users': latest_metrics.active_users,
        'total_storage_used': latest_metrics.total_storage_used,
        'last_updated': latest_metrics.updated_at,
        'recent_errors': recent_errors,
        'recent_events': recent_events
    }
    
    return Response(health_data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_system_metrics(request):
    """Generate system metrics for a specific date (admin only)"""
    date_str = request.data.get('date')
    
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        target_date = timezone.now().date()
    
    # Generate metrics
    metrics = AnalyticsService.get_system_metrics(target_date)
    
    return Response(
        SystemMetricsSerializer(metrics).data,
        status=status.HTTP_201_CREATED
    )