#!/usr/bin/env python3
import os
import sys
import hashlib

def check_dependencies():
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives import hashes
        return True
    except ImportError:
        print("[!] ERROR: 'cryptography' library is not installed.")
        print("    Please install it by running: pip install cryptography")
        print("")
        return False

def generate_keys():
    if not check_dependencies():
        sys.exit(1)
        
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    print("[*] Generating ECDSA key pair (secp256r1/prime256v1)...")
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    private_key_path = os.path.join(script_dir, "private_key.pem")
    public_key_path = os.path.join(script_dir, "public_key.pem")

    # Save Private Key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(private_key_path, "wb") as f:
        f.write(private_pem)
    print(f"[+] Saved Private Key to: {private_key_path} (KEEP THIS SECRET!)")

    # Save Public Key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(public_key_path, "wb") as f:
        f.write(public_pem)
    print(f"[+] Saved Public Key to: {public_key_path}")

    # Print C++ code snippet for esp32_cam.ino
    print("\n" + "="*80)
    print(" COPY THE C++ CODE BELOW AND PASTE IT INTO esp32_cam.ino:")
    print("="*80)
    cpp_lines = []
    for line in public_pem.decode('utf-8').strip().split('\n'):
        cpp_lines.append(f'"{line}\\n"')
    
    print("const char* ota_public_key = ")
    print("\n".join(cpp_lines) + ";")
    print("="*80 + "\n")

def sign_firmware(firmware_path):
    if not check_dependencies():
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    private_key_path = os.path.join(script_dir, "private_key.pem")

    if not os.path.exists(private_key_path):
        print(f"[!] {private_key_path} not found. Automatically generating new key pair...")
        generate_keys()
        
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives import hashes

    # Read Private Key
    print(f"[*] Reading {private_key_path}...")
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    # Read firmware file
    print(f"[*] Reading firmware file: {firmware_path}...")
    with open(firmware_path, "rb") as f:
        fw_data = f.read()

    # Sign using SHA-256
    print("[*] Signing firmware...")
    signature = private_key.sign(
        fw_data,
        ec.ECDSA(hashes.SHA256())
    )

    sig_len = len(signature)
    print(f"[+] Created signature (Size: {sig_len} bytes)")

    # Append signature and its length
    # Format: [Original binary] + [Signature] + [2 bytes signature length in big-endian]
    signed_data = fw_data + signature + sig_len.to_bytes(2, byteorder='big')
    
    output_path = firmware_path.replace(".bin", "_signed.bin")
    if output_path == firmware_path:
        output_path = firmware_path + "_signed.bin"
        
    with open(output_path, "wb") as f:
        f.write(signed_data)
        
    print(f"[+] SUCCESS! Signed firmware saved at: {output_path}")
    print(f"    Original size: {len(fw_data)} bytes")
    print(f"    Signed size  : {len(signed_data)} bytes")
    print("    -> Use this signed file to upload to ThingsBoard OTA.")

def print_usage():
    print("Usage:")
    print("  python sign_firmware.py generate         - Generate a new ECDSA key pair")
    print("  python sign_firmware.py sign <file.bin>  - Sign a firmware binary")

def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    if cmd == "generate":
        generate_keys()
    elif cmd == "sign":
        if len(sys.argv) < 3:
            print("[!] Error: Missing firmware .bin file path")
            print_usage()
            sys.exit(1)
        sign_firmware(sys.argv[2])
    else:
        print(f"[!] Invalid command: {cmd}")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
