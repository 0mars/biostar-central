from django.contrib import auth
from django.contrib import messages
from biostar.engine.const import *
from biostar.accounts.models import Profile


def engine_middleware(get_response):

    def middleware(request):

        user = request.user

        print(request.session.get(RECIPE_CLIPBOARD), "BOARD", len(request.session.get(RECIPE_CLIPBOARD)))

        # Banned and suspended users are not allowed
        if user.is_authenticated and user.profile.state in (Profile.BANNED, Profile.SUSPENDED):
            messages.error(request, f"Account is {user.profile.get_state_display()}")
            auth.logout(request)

        response = get_response(request)
        # Can process response here after its been handled by the view

        # Turn CORS on.
        response["Access-Control-Allow-Origin"] = "*"

        return response

    return middleware


