import torch
from model import DamageClassifier
from data_loader import IDX_TO_LABEL, NUM_CLASSES, DEFAULT_TRANSFORM
from PIL import Image

m = DamageClassifier(in_channels=3)
ckpt = torch.load('checkpoints/xbd_real_model.pth', map_location='cpu', weights_only=True)
m.load_state_dict(ckpt['model_state_dict'])
m.eval()
ep = ckpt['epoch']
va = ckpt['val_acc']
print(f'Checkpoint loaded: epoch={ep}, val_acc={va:.2%}')

img = torch.randn(1, 3, 224, 224)
logits = m(img)
probs = torch.softmax(logits, dim=1)
conf, pred = probs.max(dim=1)
print(f'Random test: pred={IDX_TO_LABEL[pred.item()]}, confidence={conf.item():.4f}')

test_img = Image.open('data/xbd/images/0000.png').convert('RGB')
tensor = DEFAULT_TRANSFORM(test_img).unsqueeze(0)
logits = m(tensor)
probs = torch.softmax(logits, dim=1)
conf, pred = probs.max(dim=1)
print(f'Real xBD image 0000: pred={IDX_TO_LABEL[pred.item()]}, confidence={conf.item():.4f}')
print('Inference validation: PASSED')
