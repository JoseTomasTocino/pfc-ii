from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

from siteup_frontend import views as fe_views
from siteup_api import views as api_views

urlpatterns = patterns('',

    url(r'^api/login$', api_views.LoginView.as_view(), name='api_login'),

    url(r'^$', fe_views.HomeView.as_view(), name='home'),
    url(r'^login/', fe_views.LoginView.as_view(), name="login"),
    url(r'^logout$', fe_views.LogoutView.as_view(), name="logout"),
    url(r'^password_reset$', fe_views.password_reset, name="password_reset"),
    url(r'^password_reset_done$', fe_views.password_reset_done, name="password_reset_done"),
    url(r'^password_reset_confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', fe_views.password_reset_confirm, name="password_reset_confirm"),
    url(r'^password_reset_complete/$', fe_views.password_reset_complete, name="password_reset_complete"),

    url(r'^signup/$', fe_views.SignupView.as_view(), name="signup"),
    url(r'^changepassword/$', fe_views.ChangePasswordView.as_view(), name="changepassword"),

    url(r'^profile', fe_views.ProfileView.as_view(), name="profile"),
    url(r'^dashboard', fe_views.DashboardView.as_view(), name="dashboard"),
    url(r'^get_dashboard_graph_data/(?P<check_type>\w{1,})/(?P<check_id>\d{1,})$', fe_views.get_dashboard_graph_data, name="get_dashboard_graph_data"),

    url(r'^admin/', include(admin.site.urls)),
    url(r'^groups/new', fe_views.GroupCreateView.as_view(), name="new_group"),
    url(r'^groups/edit/(?P<pk>\d{1,})', fe_views.GroupUpdateView.as_view(), name="edit_group"),
    url(r'^groups/enable/(?P<pk>\d{1,})', fe_views.GroupEnableView.as_view(), name="enable_group"),
    url(r'^groups/disable/(?P<pk>\d{1,})', fe_views.GroupDisableView.as_view(), name="disable_group"),
    url(r'^groups/delete/(?P<pk>\d{1,})', fe_views.GroupDeleteView.as_view(), name="delete_group"),

    url(r'^groups/(?P<pk>\d{1,})/addcheck/$', fe_views.ChooseCheckTypeTemplateView.as_view(), name="new_check"),
    url(r'^groups/(?P<pk>\d{1,})/addcheck/(?P<type>\w{1,})/$', fe_views.CheckCreateView.as_view(), name="new_check_next"),

    url(r'^checks/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckDetailView.as_view(), name="view_check"),
    url(r'^checks/edit/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckUpdateView.as_view(), name="edit_check"),
    url(r'^checks/delete/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckDeleteView.as_view(), name="delete_check"),
    url(r'^checks/enable/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckEnableView.as_view(), name="enable_check"),
    url(r'^checks/disable/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckDisableView.as_view(), name="disable_check"),
    url(r'^checks/export_logs/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckExportLogsView.as_view(), name="export_check_logs"),
    url(r'^checks/export_statuses/(?P<type>\w{1,})/(?P<pk>\d{1,})/$', fe_views.CheckExportStatusesView.as_view(), name="export_check_statuses"),

    url(r'^captcha/', include('captcha.urls')),

)

# DJANGO TOOLBAR

from django.conf import settings
from django.conf.urls import include, patterns, url

if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )
