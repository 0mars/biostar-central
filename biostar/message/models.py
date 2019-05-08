import logging
import mistune
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import F

from biostar.utils.shortcuts import reverse
from biostar.accounts.models import Profile
from biostar.forum import util

User = get_user_model()

# The maximum length in characters for a typical name and text field.
MAX_NAME_LEN = 256
MAX_FIELD_LEN = 1024
MAX_TEXT_LEN = 10000
MAX_LOG_LEN = 20 * MAX_TEXT_LEN

logger = logging.getLogger("engine")


class MessageManager(models.Manager):

    def get_queryset(self):
        "Regular queries exclude deleted stuff"
        return super().get_queryset().select_related("sender", "recipient",
                                                                           "sender__profile", "recipient__profile")

    def inbox_for(self, user):
        "Returns all messages that were received by the given user"
        query = self.filter(recipient=user)
        query = query.select_related("recipient", "sender", "sender__profile",
                                     "recipient__profile")

        return query

    def outbox_for(self, user):
        "Returns all messages that were sent by the given user."

        query = self.filter(sender=user)
        query = query.select_related("recipient", "sender", "sender__profile",
                                     "recipient__profile")
        return query


# Connects user to message bodies
class Message(models.Model):
    "Connects recipients to sent messages"

    MESSAGING_TYPE_CHOICES = Profile.MESSAGING_TYPE_CHOICES
    type = models.IntegerField(choices=MESSAGING_TYPE_CHOICES, default=Profile.LOCAL_MESSAGE, db_index=True)

    PROJECTS, MENTIONED, REGULAR = range(3)
    SOURCE_TYPE_CHOICES = [
                            (PROJECTS, "From project discussion"),
                            (MENTIONED, "Mentioned in a post"),
                            (REGULAR, "Regular")
                            ]
    source = models.IntegerField(choices=SOURCE_TYPE_CHOICES, default=REGULAR, db_index=True)

    objects = MessageManager()
    uid = models.CharField(max_length=32, unique=True)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="author", on_delete=models.CASCADE)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    subject = models.CharField(max_length=120)
    parent_msg = models.ForeignKey(to='self', related_name='next_messages', null=True, blank=True,
                                   on_delete=models.CASCADE)
    body = models.TextField(max_length=MAX_TEXT_LEN)
    html = models.TextField(default='', max_length= MAX_TEXT_LEN * 10)
    unread = models.BooleanField(default=True)
    sent_date = models.DateTimeField(db_index=True, null=True)

    def save(self, *args, **kwargs):
        self.html = self.html or mistune.markdown(self.body)
        super(Message, self).save(**kwargs)

    def __str__(self):
        return u"Message %s, %s" % (self.sender, self.recipient)

    @property
    def from_project(self):
        return self.source == self.PROJECTS

    @property
    def from_mentions(self):
        return self.source == self.MENTIONED

    @property
    def inbox_url(self):
        return reverse("inbox_view", kwargs=dict(uid=self.uid))

    @property
    def outbox_url(self):
        return reverse("outbox_view", kwargs=dict(uid=self.uid))


@receiver(post_save, sender=Message)
def update_new_messages(sender, instance, created, *args, **kwargs ):
    "Update the user's new_messages flag on creation"

    if created:
        # Add 1 to recipient's new messages once uponce creation
        user = instance.recipient
        msgs = F('new_messages')
        Profile.objects.filter(user=user).update(new_messages=msgs + 1)