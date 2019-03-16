from . import views
from django.conf.urls import url

urlpatterns = [

    # Post urls
    url(r'^$', views.post_list, name='post_list'),
    url(r'^view/(?P<uid>[-\w]+)/$', views.post_view, name='post_view'),

    url(r'^create/$', views.post_create, name='post_create'),
    url(r'^sub/(?P<uid>[-\w]+)/$', views.subs_action, name='subs_action'),
    url(r'^edit/(?P<uid>[-\w]+)/$', views.edit_post, name='post_edit'),
    url(r'^comment/$', views.comment, name='post_comment'),

    url(r'^vote/$', views.ajax_vote, name='vote'),


    #url(r'^tags/list/$', views.tags_list, name='tags_list'),
    url(r'moderate/(?P<uid>[-\w]+)/$', views.post_moderate, name="post_moderate"),

    # Community urls
    url(r'^community/list/$', views.community_list, name='community_list'),

]






