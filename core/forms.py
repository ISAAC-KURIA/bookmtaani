from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from .models import UserProfile, Business, BusinessHours, Service, TimeBlock, Review, CustomerNote


class RegisterForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Username'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email (optional)'}))
    full_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full name (optional)'}))
    role = forms.ChoiceField(
        choices=[('customer', 'Customer'), ('owner', 'Business Owner')],
        widget=forms.RadioSelect,
        initial='customer',
    )
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password'}))
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm password'}))

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned


class BookingDateForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
        label='Select Date',
    )


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'price', 'duration_minutes', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': '0'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': '15', 'step': '15'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }


class TimeBlockForm(forms.ModelForm):
    class Meta:
        model = TimeBlock
        fields = ['date', 'start_time', 'end_time', 'reason', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
            'reason': forms.Select(attrs={'class': 'form-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-input'}),
        }


class BusinessHoursForm(forms.Form):
    """Dynamic form for setting business hours for all 7 days."""
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        for day in range(7):
            prefix = f'day_{day}'
            self.fields[f'{prefix}_is_closed'] = forms.BooleanField(
                required=False,
                label=f'{self.DAY_NAMES[day]} - Closed',
            )
            self.fields[f'{prefix}_open'] = forms.TimeField(
                required=False,
                label='Open',
                widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
            )
            self.fields[f'{prefix}_close'] = forms.TimeField(
                required=False,
                label='Close',
                widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
            )

        if business:
            from .models import BusinessHours
            for bh in BusinessHours.objects.filter(business=business):
                d = bh.day_of_week
                prefix = f'day_{d}'
                self.fields[f'{prefix}_is_closed'].initial = bh.is_closed
                self.fields[f'{prefix}_open'].initial = bh.open_time
                self.fields[f'{prefix}_close'].initial = bh.close_time


class ReviewForm(forms.ModelForm):
    rating = forms.ChoiceField(
        choices=[(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Share your experience...'}),
        }


class CustomerNoteForm(forms.ModelForm):
    class Meta:
        model = CustomerNote
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'category', 'town', 'description', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'town': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'phone': forms.TextInput(attrs={'class': 'form-input'}),
        }


class MpesaForm(forms.Form):
    phone = forms.CharField(
        max_length=15,
        label='M-Pesa Phone Number',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+254XXXXXXXXX', 'value': '+254712345678'}),
    )
    pin = forms.CharField(
        max_length=6,
        min_length=4,
        label='M-Pesa PIN',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••', 'maxlength': '6'}),
    )
