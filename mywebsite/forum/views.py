from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect

def signup(request):

    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():

            form.save()
            username = form.cleaned_data.get('username')

            # where the fuck does it check if password1 == password2 ???
            raw_password = form.cleaned_data.get('password1')

            #print(raw_password)
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            
            return redirect('/')
    else:
        
        form = UserCreationForm()
    return render(request, 'forum/signup.html', {'form': form})

def index(request):
    return render(request, 'forum/home.html')





