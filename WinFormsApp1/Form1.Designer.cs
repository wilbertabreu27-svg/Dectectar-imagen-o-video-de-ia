namespace WinFormsApp1
{
    partial class Form1
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        // Controles añadidos manualmente
        private System.Windows.Forms.TextBox txtUsuario;
        private System.Windows.Forms.TextBox txtContrasena;
        private System.Windows.Forms.Button btnLogin;
        private System.Windows.Forms.Label lblUsuario;
        private System.Windows.Forms.Label lblContrasena;
        private System.Windows.Forms.Panel panelBox;
        private System.Windows.Forms.Panel underlineUsuario;
        private System.Windows.Forms.Panel underlineContrasena;
        private System.Windows.Forms.Timer animTimer;

        /// <summary>
        ///  Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.panelBox = new System.Windows.Forms.Panel();
            this.txtUsuario = new System.Windows.Forms.TextBox();
            this.txtContrasena = new System.Windows.Forms.TextBox();
            this.btnLogin = new System.Windows.Forms.Button();
            this.lblUsuario = new System.Windows.Forms.Label();
            this.lblContrasena = new System.Windows.Forms.Label();
            this.underlineUsuario = new System.Windows.Forms.Panel();
            this.underlineContrasena = new System.Windows.Forms.Panel();
            this.animTimer = new System.Windows.Forms.Timer();
            SuspendLayout();
            // 
            // Form1
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(800, 450);
            Name = "Form1";
            Text = "Iniciar sesión";
            BackColor = Color.FromArgb(34, 139, 34); // fondo verde
            // 
            // panelBox
            // 
            this.panelBox.BackColor = Color.FromArgb(255, 255, 153); // caja amarilla
            this.panelBox.Location = new Point(190, 115);
            this.panelBox.Name = "panelBox";
            this.panelBox.Size = new Size(420, 220);
            this.panelBox.TabIndex = 0;
            this.panelBox.Paint += panelBox_Paint;
            // 
            // lblUsuario
            // 
            this.lblUsuario.AutoSize = true;
            this.lblUsuario.Location = new Point(30, 30);
            this.lblUsuario.Name = "lblUsuario";
            this.lblUsuario.Size = new Size(55, 15);
            this.lblUsuario.Text = "Usuario:";
            // 
            // txtUsuario
            // 
            this.txtUsuario.Location = new Point(140, 25);
            this.txtUsuario.Name = "txtUsuario";
            this.txtUsuario.Size = new Size(200, 23);
            this.txtUsuario.Enter += txtUsuario_Enter;
            this.txtUsuario.Leave += txtUsuario_Leave;
            // 
            // lblContrasena
            // 
            this.lblContrasena.AutoSize = true;
            this.lblContrasena.Location = new Point(30, 90);
            this.lblContrasena.Name = "lblContrasena";
            this.lblContrasena.Size = new Size(70, 15);
            this.lblContrasena.Text = "Contraseña:";
            // 
            // txtContrasena
            // 
            this.txtContrasena.Location = new Point(140, 85);
            this.txtContrasena.Name = "txtContrasena";
            this.txtContrasena.Size = new Size(200, 23);
            this.txtContrasena.UseSystemPasswordChar = true;
            this.txtContrasena.Enter += txtContrasena_Enter;
            this.txtContrasena.Leave += txtContrasena_Leave;
            // 
            // btnLogin
            // 
            this.btnLogin.Location = new Point(160, 150);
            this.btnLogin.Name = "btnLogin";
            this.btnLogin.Size = new Size(100, 30);
            this.btnLogin.Text = "Entrar";
            this.btnLogin.UseVisualStyleBackColor = true;
            this.btnLogin.Click += btnLogin_Click;
            // 
            // underlineUsuario
            // 
            this.underlineUsuario.Location = new Point(140, 52);
            this.underlineUsuario.Size = new Size(0, 3);
            this.underlineUsuario.BackColor = Color.Gold;
            // 
            // underlineContrasena
            // 
            this.underlineContrasena.Location = new Point(140, 112);
            this.underlineContrasena.Size = new Size(0, 3);
            this.underlineContrasena.BackColor = Color.Gold;
            // 
            // animTimer
            // 
            this.animTimer.Interval = 15;
            this.animTimer.Tick += animTimer_Tick;
            // 
            // Form1
            // 
            Load += Form1_Load;
            // Añadir controles al panel
            this.panelBox.Controls.Add(this.lblUsuario);
            this.panelBox.Controls.Add(this.txtUsuario);
            this.panelBox.Controls.Add(this.underlineUsuario);
            this.panelBox.Controls.Add(this.lblContrasena);
            this.panelBox.Controls.Add(this.txtContrasena);
            this.panelBox.Controls.Add(this.underlineContrasena);
            this.panelBox.Controls.Add(this.btnLogin);
            // Añadir panel al formulario
            Controls.Add(this.panelBox);
            ResumeLayout(false);
            PerformLayout();
        }

        #endregion
    }
}
