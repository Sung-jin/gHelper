import socket
import time

def send_test_data():
    target_ip = "192.168.10.22"
    target_port = 9999

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
    print(f"Sending test packets to {target_ip}:{target_port}...")

    while True:
        message = "ALERT: Rare Item Dropped!"
        sock.sendto(message.encode(), (target_ip, target_port))
        time.sleep(2)

if __name__ == "__main__":
    send_test_data()