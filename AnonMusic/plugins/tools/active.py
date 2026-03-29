import os
import zipfile
import tempfile
import shutil
from pyrogram import Client, filters
from github import Github, BadCredentialsException, GithubException
from AnonMusic import app
from config import GIT_TOKEN as GITHUB_TOKEN

GITHUB_USERNAME = "Vibe-Bots"

COMMIT_MESSAGE = "Refactor: VibeApi Integration & Optimized Media Engine"

@app.on_message(filters.command("upload") & filters.reply)
async def upload_to_github(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: `/upload <repository_name>`", quote=True)

    repo_name = message.command[1]
    replied = message.reply_to_message

    if not replied.document or not replied.document.file_name.endswith(".zip"):
        return await message.reply("Please reply to a `.zip` file.", quote=True)

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, replied.document.file_name)

    downloading = await message.reply("Downloading zip...")
    await client.download_media(replied, file_name=zip_path)

    await downloading.edit("Unzipping...")
    extract_path = os.path.join(temp_dir, "unzipped")
    os.makedirs(extract_path, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
    except Exception as e:
        await downloading.edit(f"Error while unzipping: `{e}`")
        shutil.rmtree(temp_dir)
        return

    await downloading.edit("Validating GitHub Token...")

    try:
        gh = Github(GITHUB_TOKEN)
        user = gh.get_user()
        username = user.login
    except BadCredentialsException:
        await downloading.edit("GitHub Upload Failed: `Invalid GitHub Token!`")
        shutil.rmtree(temp_dir)
        return
    except Exception as e:
        await downloading.edit(f"GitHub Token Check Error: `{e}`")
        shutil.rmtree(temp_dir)
        return

    await downloading.edit("Uploading to GitHub...")

    try:
        # Try to get existing repository or create new one
        try:
            repo = user.get_repo(repo_name)
            repo_exists = True
            await downloading.edit(f"Repository found! Updating files...")
        except GithubException:
            repo = user.create_repo(repo_name)
            repo_exists = False
            await downloading.edit(f"New repository created! Uploading files...")

        # Track uploaded files
        total_files = sum([len(files) for _, _, files in os.walk(extract_path)])
        uploaded_files = 0
        failed_files = []
        
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, extract_path)
                
                # Normalize path for GitHub (use forward slashes)
                relative_path = relative_path.replace('\\', '/')
                
                # Skip empty files
                if os.path.getsize(full_path) == 0:
                    uploaded_files += 1
                    continue
                    
                with open(full_path, 'rb') as f:
                    content = f.read()
                
                try:
                    # Try to create new file
                    repo.create_file(relative_path, COMMIT_MESSAGE, content)
                    uploaded_files += 1
                    
                except GithubException as e:
                    if e.status == 422 and "already exists" in str(e).lower():
                        try:
                            # File exists - get current file and update
                            try:
                                contents = repo.get_contents(relative_path)
                                repo.update_file(
                                    contents.path, 
                                    COMMIT_MESSAGE, 
                                    content, 
                                    contents.sha
                                )
                                uploaded_files += 1
                            except GithubException as get_error:
                                if get_error.status == 404:
                                    # File doesn't exist, create it
                                    repo.create_file(relative_path, COMMIT_MESSAGE, content)
                                    uploaded_files += 1
                                else:
                                    failed_files.append(relative_path)
                                    await downloading.edit(f"⚠️ Failed: {relative_path}")
                        except Exception as update_error:
                            failed_files.append(relative_path)
                            await downloading.edit(f"⚠️ Failed: {relative_path} - {str(update_error)[:30]}")
                    else:
                        failed_files.append(relative_path)
                        await downloading.edit(f"⚠️ Failed: {relative_path} - {str(e)[:30]}")
                
                # Update progress
                if uploaded_files % 3 == 0 or uploaded_files == total_files:
                    progress = (uploaded_files / total_files) * 100
                    await downloading.edit(f"📤 Uploading... ({uploaded_files}/{total_files} files) {progress:.1f}%")
        
        # Final message
        action = "Updated" if repo_exists else "Uploaded"
        result_msg = f"✅ {action} to GitHub: [{repo_name}](https://github.com/{GITHUB_USERNAME}/{repo_name})\n"
        result_msg += f"📁 Success: {uploaded_files}/{total_files} files\n"
        
        if failed_files:
            result_msg += f"⚠️ Failed: {len(failed_files)} files\n"
            result_msg += f"📝 Commit: `{COMMIT_MESSAGE[:50]}...`"
        else:
            result_msg += f"📝 Commit: `{COMMIT_MESSAGE}`"
        
        await downloading.edit(result_msg, disable_web_page_preview=True)
        
    except Exception as e:
        await downloading.edit(f"❌ GitHub Upload Failed: `{str(e)[:200]}`")
    finally:
        shutil.rmtree(temp_dir)
