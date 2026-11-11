from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = 'BookMtaani Admin'
admin.site.site_title = 'BookMtaani'
admin.site.index_title = 'BookMtaani Administration'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
