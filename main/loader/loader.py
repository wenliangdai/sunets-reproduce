import os
import random
import collections
import torch
import numpy as np
# import scipy.misc as m
import scipy.io as sio

import matplotlib.pyplot as plt
from PIL import Image, ImageMath

from torch.utils import data
from torchvision.transforms import Compose, Normalize, ToTensor, Resize

from main import get_data_path


class VOC(data.Dataset):
    def __init__(self, mode, transform=None, target_transform=None, img_size=512, ignore_index=255, do_transform=False):
        self.imgs = self.preprocess(mode=mode)
        if len(self.imgs) == 0:
            raise RuntimeError('Found 0 images, please check the data set')
        self.mode = mode
        self.transform = transform
        self.target_transform = target_transform
        self.img_size = img_size if isinstance(img_size, tuple) else (img_size, img_size)
        self.ignore_index = ignore_index
        self.do_transform = do_transform
        self.filler = [0, 0, 0]
        self.n_classes = 21

    def __getitem__(self, index):
        img = None
        img_name = None
        mask = None
        if self.mode == 'test':
            img_path, img_name = self.imgs[index]
            img = Image.open(os.path.join(img_path, img_name + '.jpg')).convert('RGB')
            # if self.transform is not None:
            #     img = self.transform(img)
            # return img_name, img

        img_path, mask_path = self.imgs[index]
        img = Image.open(img_path).convert('RGB')
        if self.mode == 'train':
            mask = sio.loadmat(mask_path)['GTcls']['Segmentation'][0][0]
            mask = Image.fromarray(mask.astype(np.uint8)).convert('P')
        else:
            mask = Image.open(mask_path).convert('P')

        if self.do_transform:
            img, mask = self.further_transform(img, mask)
        else:
            img, mask = self.crop(img, mask)

        if self.transform is not None:
            img = self.transform(img)
        if self.target_transform is not None:
            mask = self.target_transform(mask)
        return img, mask

    def __len__(self):
        return len(self.imgs)
    
    def further_transform(self, img, mask):
        img, mask = self.scale(img, mask)
        img, mask = self.crop(img, mask)
        img, mask = self.flip(img, mask)
        # img, mask = self.rotate(img, mask)

        return img, mask
    
    def scale(self, img, mask, low=0.5, high=2.0):
        # 对图像造成 0.5 - 2 倍的缩放
        w, h = img.size
        resize = random.uniform(low, high)
        new_w, new_h = int(resize * w), int(resize * h)
        image_transform = Resize(size=(new_h, new_w))
        label_transform = Resize(size=(new_h, new_w), interpolation=Image.NEAREST)

        return (image_transform(img), label_transform(mask))

    def crop(self, img, mask):
        w, h = img.size
        th, tw = self.img_size

        # 如果图像尺寸小于要求尺寸
        if w < tw or h < th:
            padw, padh = max(tw - w, 0), max(th - h, 0)
            w += padw
            h += padh
            im = Image.new(img.mode, (w, h), tuple(self.filler))
            im.paste(img, (int(padw/2),int(padh/2)))
            l = Image.new(mask.mode, (w, h), self.ignore_index)
            l.paste(mask, (int(padw/2),int(padh/2)))
            img = im
            mask = l

        if w == tw and h == th:
            return img, mask

        x1 = random.randint(0, w - tw)
        y1 = random.randint(0, h - th)

        return img.crop((x1, y1, x1 + tw, y1 + th)), mask.crop((x1, y1, x1 + tw, y1 + th))
    
    def flip(self, img, mask):
        if random.random() < 0.5:
            return img.transpose(Image.FLIP_LEFT_RIGHT), mask.transpose(Image.FLIP_LEFT_RIGHT)
        return img, mask

    def rotate(self, img, mask):
        angle = random.uniform(-10, 10)

        mask = np.array(mask, dtype=np.int32) - self.ignore_index
        mask = Image.fromarray(mask)
        img = tuple([ImageMath.eval("int(a)-b", a=j, b=self.filler[i]) for i, j in enumerate(img.split())])

        mask = mask.rotate(angle, resample=Image.NEAREST)
        img = tuple([k.rotate(angle, resample=Image.BICUBIC) for k in img])

        mask = ImageMath.eval("int(a)+b", a=mask, b=self.ignore_index)
        img = Image.merge(mode='RGB', bands=tuple(
            [ImageMath.eval("convert(int(a)+b,'L')", a=j, b=self.filler[i]) for i, j in enumerate(img)]))
        
        return img, mask

    def preprocess(self, mode):
        assert mode in ['train', 'val', 'test']
        items = []
        sbd_path = get_data_path('sbd')
        voc_path = get_data_path('pascal')
        
        # Train with SBD training data
        if mode == 'train':
            img_path = os.path.join(sbd_path, 'dataset', 'img')
            mask_path = os.path.join(sbd_path, 'dataset', 'cls')
            data_list = [l.strip('\n') for l in open(os.path.join(
                sbd_path, 'dataset', 'train.txt')).readlines()]
            for it in data_list:
                item = (os.path.join(img_path, it + '.jpg'), os.path.join(mask_path, it + '.mat'))
                items.append(item)
        # Validate/Test with SBD validate/test data
        elif mode == 'val':
            img_path = os.path.join(voc_path, 'JPEGImages')
            mask_path = os.path.join(voc_path, 'SegmentationClass')
            data_list = [l.strip('\n') for l in open(os.path.join(
                voc_path, 'ImageSets', 'Segmentation', 'seg11valid.txt')).readlines()]
            for it in data_list:
                item = (os.path.join(img_path, it + '.jpg'), os.path.join(mask_path, it + '.png'))
                items.append(item)
        else:
            img_path = os.path.join(voc_path, 'JPEGImages')
            data_list = [l.strip('\n') for l in open(os.path.join(
                voc_path, 'ImageSets', 'Segmentation', 'test.txt')).readlines()]
            for it in data_list:
                items.append((img_path, it))
        return items