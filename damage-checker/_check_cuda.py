import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version (runtime): {torch.version.cuda}")
print(f"cuDNN version: {torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else 'N/A'}")
print(f"Device count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"Device 0: {torch.cuda.get_device_name(0)}")
    print(f"Device 0 memory: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")
else:
    print("WARNING: CUDA not available - training will run on CPU")
    print("Check: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
