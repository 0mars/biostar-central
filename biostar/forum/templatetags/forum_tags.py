import logging
import hashlib
import urllib.parse
import itertools
from datetime import timedelta, datetime
from django.utils.timezone import utc
from django import template
from django.utils.safestring import mark_safe
from django.core.paginator import Paginator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Q

from biostar.engine.models import Project
from biostar.utils.shortcuts import reverse
from biostar.forum.models import Post, Vote
from biostar.forum import auth, forms, models, const, util


User = get_user_model()

logger = logging.getLogger("engine")

register = template.Library()

def now():
    return datetime.utcnow().replace(tzinfo=utc)


@register.inclusion_tag('widgets/user_box.html')
def user_box(user):

    return dict(user=user)


@register.inclusion_tag('widgets/pages.html')
def pages(objs, request):

    topic = request.GET.get('tag')
    active = request.GET.get("active")

    feild_name = "active" if active else "tag"

    url = request.path
    topic = active or topic

    return dict(objs=objs, url=url, topic=topic, feild_name=feild_name)


@register.simple_tag
def get_tags_list(tags_str):

    return set(util.split_tags(tags_str))


@register.simple_tag
def gravatar(user, size=80):
    #name = user.profile.name
    if user.is_anonymous or user.profile.is_suspended:
        # Removes spammy images for suspended users
        email = 'suspended@biostars.org'.encode('utf8')
    else:
        email = user.email.encode('utf8')

    hash = hashlib.md5(email).hexdigest()

    gravatar_url = "https://secure.gravatar.com/avatar/%s?" % hash
    gravatar_url += urllib.parse.urlencode({
        's': str(size),
        'd': 'retro',
    }
    )

    return mark_safe(f"""<img src={gravatar_url} height={size} width={size}/>""")


@register.inclusion_tag('widgets/tags_banner.html', takes_context=True)
def tags_banner(context, limit=5, listing=False):

    request = context["request"]
    page = request.GET.get("page")

    tags = Post.objects.order_by("-pk").values("tags__name").annotate(Count('tags__name'))

    if listing:
        # Get the page info
        paginator = Paginator(tags, settings.TAGS_PER_PAGE)
        all_tags = paginator.get_page(page)
    else:
        all_tags = tags

    return dict(tags=all_tags, limit=limit, listing=listing, request=request)


@register.inclusion_tag('widgets/post_body.html', takes_context=True)
def post_body(context, post, user, tree, form, include_userbox=True, next_url=None,
            project_uid=None, sub_url=None):

    "Renders the post body"
    request = context['request']

    sub_url = sub_url or reverse("subs_action", request=request, kwargs=dict(uid=post.uid))
    next_url = next_url or reverse("post_view", request=request, kwargs=dict(uid=post.uid))

    return dict(post=post, user=user, tree=tree, request=request,
                form=form, include_userbox=include_userbox,
                sub_url=sub_url, next_url=next_url,
                redir_field_name=const.REDIRECT_FIELD_NAME, project_uid=project_uid)


@register.inclusion_tag('widgets/subs_actions.html')
def subs_actions(post, user, next, sub_url):

    if user.is_anonymous:
        sub = None
    else:
        sub = post.subs.filter(user=user).first()

    sub_type = models.Subscription.NO_MESSAGES if not sub else sub.type

    initial = dict(subtype=sub_type)

    form = forms.SubsForm(user=user, post=post, initial=initial)
    unsubbed = sub_type == models.Subscription.NO_MESSAGES

    button = "Follow" if unsubbed else "Update"

    return dict(post=post, form=form, button=button, next=next, sub_url=sub_url,
                redir_field_name=const.REDIRECT_FIELD_NAME)


@register.filter
def show_email(user):

    try:
        head, tail = user.email.split("@")
        email = head[0] + "*" * 10 + tail
    except:
        return user.email[0] + "*" * 10

    return email


@register.inclusion_tag('widgets/feed.html')
def feed(user):

    recent_votes = Vote.objects.filter(type=Vote.UP)[:settings.VOTE_FEED_COUNT]
    # Needs to be put in context of posts
    recent_votes = recent_votes.select_related("post")

    recent_locations = User.objects.filter(~Q(profile__location=""))
    recent_locations = recent_locations.select_related("profile").distinct()[:settings.LOCATION_FEED_COUNT]

    recent_awards = ''
    recent_replies = Post.objects.filter(type__in=[Post.COMMENT, Post.ANSWER])
    recent_replies = recent_replies.select_related("author__profile", "author")[:settings.REPLIES_FEED_COUNT]
    recent_projects = Project.objects.filter(privacy=Project.PUBLIC).order_by("-pk")[:settings.PROJECT_FEED_COUNT]

    context = dict(recent_votes=recent_votes, recent_awards=recent_awards,
                   recent_locations=recent_locations, recent_replies=recent_replies,
                   user=user, recent_projects=recent_projects)

    return context


@register.filter
def show_score_icon(score):

    icon = "small circle"
    if score > 500:
        icon = "small star"

    score_icon = f'<i class="ui {icon} icon"></i>'

    return mark_safe(score_icon)


@register.filter
def show_score(score):

    score = (score * 14) + 1
    return score


@register.inclusion_tag('widgets/user_info.html')
def user_info(post, by_diff=False, with_image=True):

    return dict(post=post, by_diff=by_diff, with_image=with_image)


@register.simple_tag
def get_thread_users(post, limit=3):

    users = post.thread_users.all()[:limit]

    return users


@register.inclusion_tag('widgets/listing.html')
def listing(posts=None):

    return dict(posts=posts)


@register.filter
def show_nonzero(value):
    "The purpose of this is to return value or empty"
    return value if value else ''


def pluralize(value, word):
    if value > 1:
        return "%d %ss" % (value, word)
    else:
        return "%d %s" % (value, word)


@register.simple_tag
def object_count(request, otype):

    user = request.user
    count = 0

    if user.is_authenticated:

        if otype == "message":
            count = user.profile.new_messages

    return count


@register.filter
def time_ago(date):

    # Rare bug. TODO: Need to investigate why this can happen.
    if not date:
        return ''
    delta = now() - date
    if delta < timedelta(minutes=1):
        return 'just now'
    elif delta < timedelta(hours=1):
        unit = pluralize(delta.seconds // 60, "minute")
    elif delta < timedelta(days=1):
        unit = pluralize(delta.seconds // 3600, "hour")
    elif delta < timedelta(days=30):
        unit = pluralize(delta.days, "day")
    elif delta < timedelta(days=90):
        unit = pluralize(int(delta.days / 7), "week")
    elif delta < timedelta(days=730):
        unit = pluralize(int(delta.days / 30), "month")
    else:
        diff = delta.days / 365.0
        unit = '%0.1f years' % diff
    return "%s ago" % unit


@register.filter
def bignum(number):
    "Reformats numbers with qualifiers as K"
    try:
        value = float(number) / 1000.0
        if value > 10:
            return "%0.fk" % value
        elif value > 1:
            return "%0.1fk" % value
    except ValueError as exc:
        pass
    return str(number)


@register.simple_tag
def boxclass(post):
    # Create the css class for each row

    if post.type == Post.JOB:
        style = "job"
    elif post.type == Post.TUTORIAL:
        style = "tutorial"
    elif post.type == Post.TOOL:
        style = "tool"
    elif post.type == Post.FORUM:
        style = "gold"
    elif post.type == Post.NEWS:
        style = "news"
    elif post.has_accepted:
        style = "accept"
    elif post.reply_count > 0:
        style = "lightgreen"
    elif post.comment_count > 0:
        style = "grey"
    else:
        style = "maroon"

    return style


@register.simple_tag
def render_comments(request, tree, post, next_url, project_uid=None,
                    comment_template='widgets/comment_body.html'):

    if post.id in tree:
        text = traverse_comments(request=request, post=post, tree=tree,
                                 comment_template=comment_template,
                                 next_url=next_url, project_uid=project_uid)
    else:
        text = ''

    return mark_safe(text)


def traverse_comments(request, post, tree, comment_template, next_url,
                      project_uid=None):
    "Traverses the tree and generates the page"

    body = template.loader.get_template(comment_template)
    comment_url = reverse("post_comment")

    def traverse(node):
        vote_url = reverse("vote")

        data = ['<div class="ui comment segments">']
        cont = {"post": node, 'user': request.user, 'request': request, "comment_url":comment_url,
                "vote_url":vote_url, "next_url":next_url, "redir_field_name":const.REDIRECT_FIELD_NAME,
                "project_uid": project_uid}
        html = body.render(cont)
        data.append(html)
        for child in tree.get(node.id, []):

            data.append(f'<div class="ui segment comment basic">')
            data.append(traverse(child))
            data.append("</div>")

        data.append("</div>")
        return '\n'.join(data)

    # this collects the comments for the post
    coll = []
    for node in tree[post.id]:
        coll.append(traverse(node))

    return '\n'.join(coll)


