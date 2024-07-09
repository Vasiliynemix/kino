from django import forms


class MyForm(forms.Form):
    chair_but = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['chair_but'].widget.attrs['value'] = 'chair'

    def clean(self):
        cleaned_data = super().clean()
        button_clicked = None
        for field_name, field_value in cleaned_data.items():
            if field_value:
                button_clicked = field_name
                break
        cleaned_data['button_clicked'] = button_clicked
        return cleaned_data
