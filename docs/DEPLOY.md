# Putting Hormonious online (PythonAnywhere)

This takes about 45 minutes the first time. You do the steps that involve accounts and
passwords; every command is explained before you run it. Text like `<you>` means "replace
with your PythonAnywhere username".

What you'll end up with: `https://<you>.pythonanywhere.com`, protected by the family
password, on both iPhones' home screens.

---

## 1. On your PC: get ready

**a) Choose the family password.** Something you'll both remember but nobody would guess
(a short phrase works well, e.g. three random words). You'll type it once per phone.

**b) Make a secret key.** This signs the login cookie so it can't be forged:

```powershell
.\.venv\Scripts\python.exe manage.py make-secret
```

It prints a long random string. Keep it handy (e.g. in Notepad) for step 4. Don't share it.

**c) Take a backup of your data.** Your recipes, plans and ratings are in `hormonious.db`.
Stop the app first (Ctrl+C), then:

```powershell
.\.venv\Scripts\python.exe manage.py backup
```

It saves a dated copy in the `backups` folder. You'll upload that copy in step 4.

## 2. Create the PythonAnywhere account

1. Go to **pythonanywhere.com** → **Pricing & signup** → **Create a Beginner account** (free).
2. Your username becomes the web address, e.g. username `hormonious` → `hormonious.pythonanywhere.com`.
3. Confirm your email address.

## 3. Copy the code from GitHub

The repository is private, so PythonAnywhere needs permission to read it. Free accounts
can only reach GitHub over https, so we use a read-only **access token** (a password just
for this).

**a) Make the token on GitHub:** your profile picture → **Settings** → **Developer settings**
→ **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
- Name: `PythonAnywhere`. Expiration: 1 year.
- Repository access: **Only select repositories** → `dajones91/hormonious`.
- Permissions → Repository permissions → **Contents: Read-only**. Nothing else.
- Generate, and copy the token (starts `github_pat_`). It's shown once.

**b) On PythonAnywhere:** **Consoles** → **Bash**. A black terminal opens in your browser. Type:

```bash
git clone https://github.com/dajones91/hormonious.git
```

*Copies the code into a folder called `hormonious`.* When asked:
- **Username:** `dajones91`
- **Password:** paste the token (nothing appears as you paste, that's normal), then Enter.

```bash
cd hormonious
git config credential.helper store
```

*Moves into the folder, and remembers the token so future updates don't ask again (it's
stored in your private PythonAnywhere home folder).*

**c) Create the app's private Python environment and install the libraries** (a few minutes):

```bash
mkvirtualenv --python=python3.13 hormonious
pip install -r requirements.txt
```

*`mkvirtualenv` makes a private set of libraries for the app (like `.venv` on your PC);
`pip install` installs everything in `requirements.txt`.* If it says python3.13 isn't
available, use `python3.12` instead (and pick the same version in step 5).

## 4. Secrets and data

**a) The secrets file.** Still in the Bash console:

```bash
cp .env.example .env
nano .env
```

*Copies the template and opens it in a simple text editor.* Fill in, using the arrow keys:
- `SECRET_KEY=` the string from step 1b
- `FAMILY_PASSWORD=` the password from step 1a
- `ANTHROPIC_API_KEY=` your Anthropic key (the same one as on your PC, or make a new one
  called "Hormonious online")
- leave `DATABASE_URL=` empty

Save with **Ctrl+O**, Enter, then exit with **Ctrl+X**.

**b) Your data.** **Files** tab → open the `hormonious` folder → **Upload a file** → choose the
backup from step 1c (in your project's `backups` folder). Then, back in the Bash console,
rename it to the name the app expects (use the actual file name you uploaded):

```bash
mv hormonious-2026-*.db hormonious.db
```

**c) Quick check** (no cost):

```bash
python manage.py recipes | tail -1
```

*Should say something like "47 of 47 recipes can go on the menu". That proves the code, the
libraries and your data all work together.*

## 5. Create the web app

1. **Web** tab → **Add a new web app** → Next → **Manual configuration** → choose
   **Python 3.13** (the same version as step 3c) → Next.
2. On the web app's page, fill in:
   - **Source code:** `/home/<you>/hormonious`
   - **Working directory:** `/home/<you>/hormonious`
   - **Virtualenv:** type `hormonious` and press Enter (it becomes `/home/<you>/.virtualenvs/hormonious`)
3. **WSGI configuration file:** click the link near the top of the Web tab. Delete
   everything in it and replace it with these three lines, then **Save**:

   ```python
   import sys
   sys.path.insert(0, "/home/<you>/hormonious")
   from wsgi import application
   ```

4. **Static files:** add one row — URL `/static/`, Directory `/home/<you>/hormonious/app/static/`
5. **Security:** switch on **Force HTTPS** (the slider), so the login is always encrypted.
   *Check as you go:* if it won't switch on, tell me what it says.
6. Click the big green **Reload** button at the top.

## 6. Try it

1. Open `https://<you>.pythonanywhere.com` on your PC. You should see the login page.
2. Log in, pick **Dale**, and click around: Week, Recipes, a recipe card, Shopping.
3. Try **✨ Create a new recipe with AI** once (about 10p). If it says it couldn't reach the
   Anthropic API, tell me: free accounts reach the internet through a proxy, and I may need
   to adjust a setting.

If you see "Something went wrong", the **Error log** link on the Web tab says why — copy the
last few lines to me.

## 7. Add it to both iPhones

On each phone:

1. Open **Safari** (it must be Safari) and go to `https://<you>.pythonanywhere.com`.
2. Log in with the family password, then tap your name.
3. Tap the **Share** button (square with an arrow) → **Add to Home Screen** → **Add**.
4. Open it from the home screen: it opens full-screen with the Hormonious icon, and "Keep
   screen on" now works on recipe cards.

You'll stay logged in for about six months on each phone.

---

## Looking after it

**From now on, the online app is the real one.** Plan, rate and shop there. The copy on your
PC is for trying changes; it won't see what you do online.

**Updating after I make changes** (Bash console on PythonAnywhere):

```bash
cd ~/hormonious && workon hormonious
git pull
pip install -r requirements.txt
```

*Gets the latest code and any new libraries.* Then **Web** tab → **Reload**. Database changes
apply themselves when the app restarts, without touching your data.

**Backups** (do this every few weeks, and before any update):

```bash
cd ~/hormonious && workon hormonious && python manage.py backup
```

Then **Files** tab → `hormonious/backups` → download the newest file to your PC.

**Keep it switched on:** free web apps need a click every few months. *Check as you go:* on
the Web tab, look for a button like **"Run until 3 months from today"** and an expiry date;
put a reminder in your calendar a week before. PythonAnywhere also emails you before it
switches off.

**Costs:** hosting is free. AI recipes and imports use your Anthropic credit (about 10–30p
each).

**If you change a secret** (password, API key): edit `.env` with `nano .env`, then **Reload**.
Changing `SECRET_KEY` logs both phones out.
