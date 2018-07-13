import os
import sys
import time
import copy
import argparse
import datetime


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib

import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils, models

from dataloader import FaceScrubDataset, TripletFaceScrub, SiameseFaceScrub
from dataloader import FaceScrubBalancedBatchSampler

from losses import ContrastiveLoss, TripletLoss, OnlineTripletLoss
from networks import *

import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler

parser = argparse.ArgumentParser()

parser.add_argument("-j", "--job-number", dest="job_number", help="job number to store weights", type=int)
parser.add_argument("-e", "--epochs", dest="epochs", default=20, type=int, help="Number of epochs")
parser.add_argument("-r", "--resume-training", dest="resume", action="store_true", help="Resume training")
parser.set_defaults(resume=False)
parser.add_argument("-nc", "--no-cuda", dest='use_cuda', action='store_false', help="Do not use cuda")
parser.set_defaults(use_cuda=True)
parser.add_argument("-d", "--data-path", dest="data_path", help="path to data files")

args = parser.parse_args()

DATA_PATH = '/home/s1791387/facescrub-data/new_data_max/' if args.data_path is None else args.data_path
TRAIN_PATH = os.path.join(DATA_PATH, 'train_full_with_ids.txt')
VALID_PATH = os.path.join(DATA_PATH, 'val_full_with_ids.txt')
TEST_PATH = os.path.join(DATA_PATH, 'test_full_with_ids.txt')

CURR_DATE = "{}_{}_{}".format(time.strftime("%b"), time.strftime("%d"), time.strftime("%H"))
JOB_NUMBER = "{}_{}".format(args.job_number, CURR_DATE) if args.job_number is not None else CURR_DATE
WEIGHTS_PATH = '/home/s1791387/model_weigths/job_{}/'.format(JOB_NUMBER)

# hyper parameters
batch_size = 4
input_size = 299
output_dim = 128
learning_rate = 1e-3
num_epochs = args.epochs
print_every = 100
best_accuracy = torch.FloatTensor([0])
start_epoch = 0

use_cuda = args.use_cuda
cuda = False
# if gpu is to be used
if use_cuda and torch.cuda.is_available():
    device = torch.device("cuda")
    torch.set_default_tensor_type('torch.cuda.FloatTensor')
    cuda = True
else:
    device = torch.device("cpu")

print('Device set: {}'.format(device))
print('Training set path: {}'.format(TRAIN_PATH))
print('Training set Path exists: {}'.format(os.path.isfile(TRAIN_PATH)))

data_transforms = {
    'train': transforms.Compose([
        transforms.Resize((299, 299)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ]),
    'val': transforms.Compose([
        transforms.Resize((299, 299)),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
}


train_df = FaceScrubDataset(
    txt_file=TRAIN_PATH, root_dir=DATA_PATH, transform=data_transforms['train'])

print('Train data loaded from {}. Length: {}'.format(TRAIN_PATH, len(train_df)))
triplet_train_df = TripletFaceScrub(train_df, train=True)
print('Train data converted to triplet data')


triplet_dataloader = torch.utils.data.DataLoader(
    triplet_train_df, batch_size=4, shuffle=True, num_workers=1)


inception = models.inception_v3(pretrained=True)
inception.aux_logits = False
num_ftrs = inception.fc.in_features
inception.fc = torch.nn.Linear(num_ftrs, 128)

tripletinception = TripletNet(inception)

params = list(tripletinception.parameters())
print('Number of params in triplet inception: {}'.format(len(params)))

tripletinception.train()

margin = 1.
criterion = nn.TripletMarginLoss(margin=margin, p=2)

lr = 1e-2
optimizer = optim.Adam(tripletinception.parameters(), lr=lr)
scheduler = lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.1)

n_epochs = 20

triplet_dataloader = torch.utils.data.DataLoader(
    triplet_train_df, batch_size=4, shuffle=True, num_workers=4)
print('length of dataset {}'.format(len(triplet_train_df)))
tripletinception.train()

if cuda:
    tripletinception.cuda()
    print('sent model to gpu {}'.format(
        next(tripletinception.parameters()).is_cuda))

print('length of dataloader: {}'.format(len(triplet_dataloader)))

for epoch in range(n_epochs):
    print('Epoch {}/{}'.format(epoch, n_epochs - 1))
    print('-' * 10)

    running_loss = 0.0

    for i, (imgs, labels) in enumerate(triplet_dataloader):
        optimizer.zero_grad()
        imgs = [img.to(device) for img in imgs]
        embed_anchor, embed_pos, embed_neg = tripletinception(
            imgs[0], imgs[1], imgs[2])

        loss = criterion(embed_anchor, embed_pos, embed_neg)

        loss.backward()
        optimizer.step()

        running_loss += loss.item()

        if i % 500 == 0:
            print('epoch number: {} batch number: {} loss: {}'.format(epoch, i, running_loss/500))

    state = {
        'epoch': epoch,
        'state_dict': tripletinception.state_dict(),
        'optimizer': optimizer.state_dict(),
        'scheduler': scheduler.state_dict()
    }


    MODEL_NAME = WEIGHTS_PATH + 'weights_{}.pth'.format(epoch)
    if not os.path.exists(WEIGHTS_PATH):
        os.makedirs(WEIGHTS_PATH)
    torch.save(state, MODEL_NAME)
    print('saved model to {}'.format(MODEL_NAME))

print('finished training')
