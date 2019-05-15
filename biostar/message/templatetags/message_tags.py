import logging
from django import template
from biostar.message import const, models

logger = logging.getLogger("engine")

register = template.Library()


@register.simple_tag
def get_all_message_count(request):

    user = request.user
    outbox = inbox = projects = mentioned = unread = 0

    if user.is_authenticated:
        inbox = models.Message.objects.inbox_for(user=user)
        outbox = models.Message.objects.outbox_for(user=user).count()
        unread = inbox.filter(unread=True).count()
        mentioned = inbox.filter(source=models.Message.MENTIONED).count()

    context = dict(outbox=outbox, inbox=inbox.count(), projects=projects, mentioned=mentioned,
                   unread=unread)

    return context


@register.inclusion_tag("widgets/message_top_actionbar.html", takes_context=True)
def message_top_actionbar(context, with_pages=False):
    extra_context = dict(with_pages=with_pages)
    context.update(extra_context)
    return context


@register.simple_tag
def is_unread(user, message):

    if message.recipient == user and message.unread:
        return "unread-message"

    return ""


@register.simple_tag
def is_inbox(message, target):

    return message.recipient == target


@register.inclusion_tag("widgets/message_menu.html")
def message_menu(extra_tab=None, request=None):

    extra = {extra_tab: "active"}
    context = dict(request=request, active_tab=const.ACTIVE_MESSAGE_TAB,
                   const_in=const.INBOX, const_out=const.OUTBOX,
                   const_unread=const.UNREAD)
    context.update(extra)
    return context
