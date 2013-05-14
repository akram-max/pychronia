# -*- coding: utf-8 -*-

from django.conf.urls.defaults import *
from django.contrib import admin
from django.conf import settings

admin.autodiscover()

urlpatterns = patterns('',
    (r'^admin/', include(admin.site.urls)),

    (r'^i18n/', include('django.conf.urls.i18n')), # to set language

    ## (r'^accounts/', include('registration.backends.default.urls')), # two steps user registration with django-registration
    (r'^accounts/', include('userprofiles.urls')), # one-step registration

    url(r'^weblog/', include('zinnia.urls')), # TOO MANY URLS, but required by cms menu integration

    #url(r'^comments/', include('django.contrib.comments.urls')), useless ATM ?

    (r'^aa/', include('cms.urls')), # this MUST end with '/' or be empty
)


#from pprint import pprint
#pprint(urlpatterns)

''' UNUSED MODULES
    # Uncomment the admin/doc line below and add 'django.contrib.admindocs'
    # to INSTALLED_APPS to enable admin documentation:
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),

    #(r'^admin/filebrowser/', include('filebrowser.urls')), # TO BE PUT BEFORE "admin/" !!
    
    
    # specific zinnia parts
   url(r'^weblog/categories/', include('zinnia.urls.categories')),
    url(r'^weblog/', include('zinnia.urls.entries')),
    url(r'^weblog/', include('zinnia.urls.archives')),
    #url(r'^feeds/', include('zinnia.urls.feeds')),


'''
