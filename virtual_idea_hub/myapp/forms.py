from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class UserLoginForm(forms.Form):
    username = forms.CharField(max_length=100)
    password = forms.CharField(widget=forms.PasswordInput())

class UserRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput())
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput())
    first_name = forms.CharField(max_length=30, required=True, label='First Name')
    last_name = forms.CharField(max_length=30, required=True, label='Last Name')
    email = forms.EmailField(required=True, label='Email')
    phone_number = forms.CharField(max_length=15, required=False, label='Phone Number')
    receive_otp_via_sms = forms.BooleanField(required=False, label='Receive OTP via SMS')

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'receive_otp_via_sms']
        labels = {
            'username': 'Username',
        }
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Enter your username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Enter your email'}),
            'phone_number': forms.TextInput(attrs={'placeholder': 'Enter your phone number'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 != password2:
            raise forms.ValidationError("Passwords do not match")