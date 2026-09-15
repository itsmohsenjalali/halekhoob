from django import forms

from .models import Mood, Video
from .validation import canonical_source


class VideoForm(forms.ModelForm):
    new_mood = forms.CharField(label="حس تازه (اختیاری)", max_length=40, required=False)

    class Meta:
        model = Video
        fields = ["title", "moods", "note"]
        widgets = {
            "moods": forms.CheckboxSelectMultiple(),
            "note": forms.Textarea(attrs={"rows": 4}),
            "title": forms.TextInput(attrs={"placeholder": "نامی که یادت می‌ماند"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moods"].required = False

    def clean(self):
        data = super().clean()
        if not data.get("moods") and not data.get("new_mood"):
            self.add_error("moods", "حداقل یک حس انتخاب کن یا یک حس تازه بساز.")
        return data

    def save_moods(self, video):
        video.moods.set(self.cleaned_data["moods"])
        name = self.cleaned_data.get("new_mood", "").strip()
        if name:
            video.moods.add(Mood.objects.get_or_create(name=name)[0])


class AddForm(VideoForm):
    source_url = forms.URLField(
        label="لینک ویدیو",
        max_length=1000,
        assume_scheme="https",
        widget=forms.URLInput(attrs={"dir": "ltr", "placeholder": "https://…", "autofocus": True}),
    )

    def clean_source_url(self):
        self.source = canonical_source(self.cleaned_data["source_url"])
        return self.source[2]


class MoodForm(forms.ModelForm):
    class Meta:
        model = Mood
        fields = ["name"]
