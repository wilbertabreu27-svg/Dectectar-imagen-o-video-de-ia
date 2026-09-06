using Microsoft.Maui.Controls;
using System.Threading.Tasks;

namespace MauiLoginApp
{
    public partial class MainPage : ContentPage
    {
        public MainPage()
        {
            InitializeComponent();

            usernameEntry.Focused += UsernameEntry_Focused;
            usernameEntry.Unfocused += UsernameEntry_Unfocused;
            passwordEntry.Focused += PasswordEntry_Focused;
            passwordEntry.Unfocused += PasswordEntry_Unfocused;
            btnLogin.Clicked += BtnLogin_Clicked;
        }

        private async void UsernameEntry_Focused(object sender, FocusEventArgs e)
        {
            await underlineUser.ScaleTo(1, 200, Easing.CubicOut);
            await card.TranslateTo(-6, 0, 100);
        }

        private async void UsernameEntry_Unfocused(object sender, FocusEventArgs e)
        {
            await underlineUser.ScaleTo(0, 200, Easing.CubicIn);
            await card.TranslateTo(0, 0, 100);
        }

        private async void PasswordEntry_Focused(object sender, FocusEventArgs e)
        {
            await underlinePassword.ScaleTo(1, 200, Easing.CubicOut);
            await card.TranslateTo(6, 0, 100);
        }

        private async void PasswordEntry_Unfocused(object sender, FocusEventArgs e)
        {
            await underlinePassword.ScaleTo(0, 200, Easing.CubicIn);
            await card.TranslateTo(0, 0, 100);
        }

        private async void BtnLogin_Clicked(object sender, System.EventArgs e)
        {
            var usuario = usernameEntry.Text ?? string.Empty;
            var contrasena = passwordEntry.Text ?? string.Empty;

            if (usuario == "admin" && contrasena == "1234")
            {
                await DisplayAlert("Bienvenido", "Inicio de sesión exitoso", "OK");
            }
            else
            {
                await DisplayAlert("Error", "Usuario o contraseña incorrectos", "OK");
            }
        }
    }
}
