from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("api/audio-playlist/", views.audio_playlist, name="audio_playlist"),
    path("", views.home, name="home"),
    path("archive/", views.archive, name="archive"),
    path("add/", views.add, name="add"),
    path("moods/", views.moods, name="moods"),
    path("videos/<int:pk>/", views.detail, name="detail"),
    path("videos/<int:pk>/edit/", views.edit, name="edit"),
    path("videos/<int:pk>/favorite/", views.favorite, name="favorite"),
    path("videos/<int:pk>/retry/", views.retry, name="retry"),
    path("videos/<int:pk>/delete/", views.delete, name="delete"),
    path("videos/<int:pk>/media/<str:kind>/", views.media, name="media"),
    path("api/videos/<int:pk>/status/", views.status, name="status"),
]
