import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import configparser
from cryptography.fernet import Fernet

class IniEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("INI File Editor")
        self.config = configparser.ConfigParser()
        self.fernet = None

        # Set up the GUI layout
        load_button = tk.Button(self.root, text="Load INI File", command=self.load_ini)
        load_button.pack(pady=20)

        save_button = tk.Button(self.root, text="Save Changes", command=self.save_changes)
        save_button.pack(pady=20)

        self.entries = {}
        self.values_frame = tk.Frame(self.root)
        self.values_frame.pack(pady=20)

    def load_ini(self):
        file_path = filedialog.askopenfilename(title="Select INI File",
                                               filetypes=(("INI Files", "*.ini"), ("All Files", "*.*")))
        if not file_path:
            return

        key = simpledialog.askstring("Encryption Key", "Enter the encryption key:", show="*")
        if not key:
            return

        self.fernet = Fernet(key)
        self.config.read(file_path)
        self.display_decrypted_values()

    def display_decrypted_values(self):
        for widget in self.values_frame.winfo_children():
            widget.destroy()

        for section in self.config.sections():
            for option in self.config[section]:
                frame = tk.Frame(self.values_frame)
                frame.pack(fill=tk.X)

                label = tk.Label(frame, text=f"{section}.{option}:")
                label.pack(side=tk.LEFT)

                decrypted_value = self.fernet.decrypt(self.config[section][option].encode()).decode()
                entry = tk.Entry(frame)
                entry.insert(0, decrypted_value)
                entry.pack(side=tk.LEFT, expand=True, fill=tk.X)

                delete_button = tk.Button(frame, text="Delete", command=lambda s=section, o=option, f=frame: self.delete_option(s, o, f))
                delete_button.pack(side=tk.RIGHT)

                self.entries[(section, option)] = entry

    def delete_option(self, section, option, frame):
        del self.config[section][option]
        frame.pack_forget()  # Remove the frame from the GUI
        if not self.config[section]:
            del self.config[section]  # Remove empty sections

    def save_changes(self):
        with filedialog.asksaveasfile(mode='w', defaultextension=".ini", filetypes=[("INI Files", "*.ini")]) as file:
            if file:
                self.config.write(file)
                messagebox.showinfo("Success", "Changes saved successfully.")

if __name__ == "__main__":
    root = tk.Tk()
    app = IniEditorApp(root)
    root.mainloop()
