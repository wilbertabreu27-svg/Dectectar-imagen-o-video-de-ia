using System;
using System.Windows.Forms;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace WinFormsApp1
{
    public partial class Form1 : Form
    {
        // Animación y estado
        private int targetWidthUsuario = 0;
        private int currentWidthUsuario = 0;
        private int targetWidthContrasena = 0;
        private int currentWidthContrasena = 0;
        private readonly Point panelBaseLocation = new Point(190, 115);
        private int panelOffsetTarget = 0;
        private int panelOffset = 0;
        public Form1()
        {
            InitializeComponent();
        }

        private void Form1_Load(object sender, EventArgs e)
        {
            // Inicialización al cargar el formulario
        }

        private void txtUsuario_Enter(object sender, EventArgs e)
        {
            targetWidthUsuario = txtUsuario.Width;
            panelOffsetTarget = -6;
            animTimer.Enabled = true;
        }

        private void txtUsuario_Leave(object sender, EventArgs e)
        {
            targetWidthUsuario = 0;
            panelOffsetTarget = 0;
            animTimer.Enabled = true;
        }

        private void txtContrasena_Enter(object sender, EventArgs e)
        {
            targetWidthContrasena = txtContrasena.Width;
            panelOffsetTarget = -6;
            animTimer.Enabled = true;
        }

        private void txtContrasena_Leave(object sender, EventArgs e)
        {
            targetWidthContrasena = 0;
            panelOffsetTarget = 0;
            animTimer.Enabled = true;
        }

        private void animTimer_Tick(object? sender, EventArgs e)
        {
            bool changed = false;
            // Smoothly approach target widths
            if (currentWidthUsuario < targetWidthUsuario)
            {
                currentWidthUsuario = Math.Min(targetWidthUsuario, currentWidthUsuario + 12);
                changed = true;
            }
            else if (currentWidthUsuario > targetWidthUsuario)
            {
                currentWidthUsuario = Math.Max(targetWidthUsuario, currentWidthUsuario - 12);
                changed = true;
            }

            if (currentWidthContrasena < targetWidthContrasena)
            {
                currentWidthContrasena = Math.Min(targetWidthContrasena, currentWidthContrasena + 12);
                changed = true;
            }
            else if (currentWidthContrasena > targetWidthContrasena)
            {
                currentWidthContrasena = Math.Max(targetWidthContrasena, currentWidthContrasena - 12);
                changed = true;
            }

            if (panelOffset < panelOffsetTarget)
            {
                panelOffset = Math.Min(panelOffsetTarget, panelOffset + 2);
                changed = true;
            }
            else if (panelOffset > panelOffsetTarget)
            {
                panelOffset = Math.Max(panelOffsetTarget, panelOffset - 2);
                changed = true;
            }

            // Aplicar valores
            if (underlineUsuario != null)
            {
                underlineUsuario.Width = currentWidthUsuario;
                underlineUsuario.Left = txtUsuario.Left;
            }
            if (underlineContrasena != null)
            {
                underlineContrasena.Width = currentWidthContrasena;
                underlineContrasena.Left = txtContrasena.Left;
            }

            if (panelBox != null)
            {
                panelBox.Location = new Point(panelBaseLocation.X + panelOffset, panelBaseLocation.Y);
            }

            if (!changed)
            {
                animTimer.Enabled = false;
            }
        }

        private void panelBox_Paint(object? sender, PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            var rect = panelBox.ClientRectangle;
            rect.Inflate(-2, -2);
            using (var path = RoundedRect(rect, 12))
            using (var pen = new Pen(Color.FromArgb(150, 0, 0, 0), 3))
            {
                g.DrawPath(pen, path);
            }
        }

        private GraphicsPath RoundedRect(Rectangle bounds, int radius)
        {
            var path = new GraphicsPath();
            int d = radius * 2;
            path.AddArc(bounds.X, bounds.Y, d, d, 180, 90);
            path.AddArc(bounds.Right - d, bounds.Y, d, d, 270, 90);
            path.AddArc(bounds.Right - d, bounds.Bottom - d, d, d, 0, 90);
            path.AddArc(bounds.X, bounds.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        private void btnLogin_Click(object? sender, EventArgs e)
        {
            string usuario = txtUsuario.Text;
            string contrasena = txtContrasena.Text;

            // Ejemplo de validación simple
            if (usuario == "admin" && contrasena == "1234")
            {
                MessageBox.Show("Inicio de sesión exitoso", "Bienvenido", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            else
            {
                MessageBox.Show("Usuario o contraseña incorrectos", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
