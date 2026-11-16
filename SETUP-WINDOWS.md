# Stockbook — Setup Guide for Your Shop Computer

This guide turns your shop's Windows computer into the app's server.
**All your data stays on that computer.** No outside company stores it.

You need:
- The Windows computer at the shop (**Windows 10 or 11**), connected to the internet
- About **30 minutes** for the first setup
- Your phone

---

## Part 1 — Put the app on the computer (one time)

1. On the shop computer, open the app's GitHub page in a browser and sign in to GitHub.
2. Click the green **Code** button, then **Download ZIP**.
3. Open your **Downloads** folder, right-click the ZIP file and choose **Extract All…**
4. Move the extracted folder somewhere permanent and easy to find, for example
   `C:\Stockbook`. *(Don't leave it in Downloads, where it's easy to delete by accident.)*

## Part 2 — Run the setup (one time)

1. Open the `C:\Stockbook` folder.
2. **Right-click `1-Setup.bat`** and choose **Run as administrator**.
   Click **Yes** if Windows asks for permission.
   *If Windows shows a blue box saying "Windows protected your PC", click **More info**, then **Run anyway**.*
3. Follow the questions in the black window:
   - If Python is missing, the setup installs it for you. When it says so,
     **close the window and run `1-Setup.bat` as administrator again**.
   - It asks you to create the **admin login** (for you or your father).
     Pick a username, for example `papa`, and a password.
     *(The password doesn't appear as you type. That's normal.)*
   - It asks whether to turn off sleep. Press **Y**. The computer must stay
     awake for the app to work.
4. When you see **SETUP COMPLETE**, press any key.

## Part 3 — Start the app

1. Double-click **`2-Start-Stockbook.bat`**.
2. A black window opens and shows addresses like:

   ```
   On this computer:  http://localhost:8000
   Shop Wi-Fi:        http://192.168.1.5:8000
   ```

3. **Keep this window open.** You can minimise it, but closing it stops the app.
4. From now on, the app **starts by itself** whenever the computer is turned on
   and you log in to Windows.

## Part 4 — Open it on a phone at the shop

1. Connect the phone to the **shop Wi-Fi**.
2. Open Chrome and type the **Shop Wi-Fi** address from the black window,
   for example `http://192.168.1.5:8000`.
3. Log in with the admin username and password you created.
4. **Tip:** in Chrome's ⋮ menu choose **Add to Home screen**. The app then
   opens like a normal phone app.

> If the address stops working one day, look at the black window again.
> Your router may have given the computer a new address.

## Part 5 — Set up your shop

1. **Settings → Team accounts:** create a login for your father and one for each employee
   (choose **Employee** for staff).
2. **Settings → Suppliers:** add your suppliers. *(Optional: importing from Tally creates them automatically.)*
3. **Medicine Database → Import from Tally:** this learns which item comes from which party
   using your purchase bills. In Tally Prime: **Gateway of Tally → Alt+E (Export) → Transactions**,
   choose voucher type **Purchase**, choose the dates, set **File Format: XML (Data Interchange)**, then **Send**.
   Pick that `.xml` file in the app. If an item comes from several parties, all of them are remembered.
   The most-used party becomes the default, and the others show as **"Also from"** on the board.
   Importing the same file again is safe, because bills are never counted twice.
4. *(Optional)* **Import CSV/Excel** still works for a plain list with the columns **Name**, **Company** and **Supplier**.

## Part 6 — Use it from anywhere (home, mobile data)

This uses **Tailscale**, a free program that creates a private, encrypted
connection between your phones and the shop computer. Tailscale **can't see
or store your data**. It only helps your devices find each other.

1. On the **shop computer**: go to **tailscale.com/download**, install Tailscale for Windows,
   and sign in (for example with your Google account).
2. On **your phone**: install **Tailscale** from the Play Store / App Store and sign in
   **with the same account**. Turn it on.
3. Do the same on your father's phone.
4. In the black Stockbook window, close it and start `2-Start-Stockbook.bat` again.
   You'll now see a line like:

   ```
   Tailscale (anywhere): http://100.101.102.103:8000
   ```

5. On the phone, with Tailscale switched on, open that address. It works over
   mobile data, home Wi-Fi, anywhere.

*Employees who only use the app at the shop don't need Tailscale. The shop Wi-Fi address is enough.*

---

## Backups (very important)

- A backup is made **automatically every time the app starts** and **every day at 9:00 PM**
  (if the computer is on).
- Backups are saved in `C:\Stockbook\backend\backups`. The last 60 are kept.
- To back up right now, double-click **`Backup-Now.bat`**.
- **Strongly recommended:** keep backups on a **USB drive or second disk**, so a dead hard
  disk doesn't take your data with it:
  1. Plug in the USB drive and note its letter (for example `E:`).
  2. Open `C:\Stockbook\backend\.env` with Notepad.
  3. Change the line `# BACKUP_DIR=E:\StockbookBackups` to `BACKUP_DIR=E:\StockbookBackups`
     (remove the `#`), then save.
- Your live data is the single file `C:\Stockbook\backend\data\stockbook.db`.

### Restoring a backup
1. Close the black Stockbook window.
2. Open a Command Prompt in `C:\Stockbook\backend` and run:
   `.venv\Scripts\python.exe manage.py restore backups\stockbook-2026-11-14_210000.db`
   (use the name of the backup you want).
3. Start `2-Start-Stockbook.bat` again.

---

## Common problems

| Problem | Fix |
|---|---|
| Forgot the admin password | Double-click **`Reset-Admin-Password.bat`** and type the admin username and a new password. |
| An employee forgot their password | Admin: **Settings → Team accounts → 🔑 key icon** next to their name. |
| Phone says "site can't be reached" | Check the black window is open, the phone is on shop Wi-Fi (or Tailscale is on), and the address matches the black window. |
| Black window says the address is already in use | The app is already running (it auto-starts). Close the extra window. |
| Computer was restarted | Log in to Windows. The app starts by itself. |

## Updating the app later

1. Close the black Stockbook window.
2. Download the new ZIP and extract it.
3. Copy the new files **over** your `C:\Stockbook` folder, choosing **Replace**.
   **Never delete the `backend\data` or `backend\backups` folders.** They hold your data.
4. Run `1-Setup.bat` as administrator again. It's safe, nothing is lost.
   When it asks for the admin login, you can type your existing username to keep it (or set a new password).
