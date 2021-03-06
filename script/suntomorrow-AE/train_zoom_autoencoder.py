#!/usr/bin/env python
"""Chainer example: autoencoder of a solar image.
"""

# c.f.
# http://nonbiri-tereka.hatenablog.com/entry/2015/06/21/220506
# http://qiita.com/kenmatsu4/items/99d4a54d5a57405ecaf8

import argparse
from astropy.io import fits
import numpy as np
import scipy.ndimage.interpolation as intp
import math as M
import operator
import os
import re
import six
import subprocess
import random
import pickle

import chainer
from chainer import computational_graph as c
from chainer import cuda, Variable, FunctionSet, optimizers
import chainer.functions as F
from chainer import optimizers

import matplotlib as mpl
mpl.use('Agg')
import pylab
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import AxesGrid

from datetime import datetime


global dlDepth
global  global_normalization, work_dir, epoch_per_level, training_mode_string
dlDepth = 10
global_normalization = 1e-2
dl_batch_size = 2
epoch_per_level = 6000
training_mode_string = 'i'

parser = argparse.ArgumentParser(description='Chainer example: MNIST')
parser.add_argument('--gpu', '-g', default=-1, type=int,
                    help='GPU ID (negative value indicates CPU)')
args = parser.parse_args()

global gpu_flag
gpu_flag=(args.gpu >= 0)
if gpu_flag:
    cuda.init(args.gpu)


def system(cmd):
    subprocess.call(cmd, shell=True)


global work_dir
work_dir='/home/ubuntu/public_html/' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
system('mkdir -p ' + work_dir)

log_train_fn = work_dir + '/log-training.txt'
log_test_fn = work_dir + '/log-test.txt'

system('cp {} {} '.format(__file__, work_dir))

def plot_img(img4,fn,title_str):
    global  global_normalization, work_dir
    global dlDepth, training_mode_string 
    print np.shape(img4)

    if gpu_flag :
        img4 = cuda.to_cpu(img4)

    img=(1.0/ global_normalization)*img4[0][0]

    dpi=200
    plt.figure(figsize=(8,6),dpi=dpi)
    fig, ax = plt.subplots()
	
	
    circle1=plt.Circle((512,512),450,edgecolor='black',fill=False)
	
    cmap = plt.get_cmap('bwr')
    cax = ax.imshow(img,cmap=cmap,extent=(0,1024,0,1024),vmin=-100.0,vmax=100.0)
    cbar=fig.colorbar(cax)
    fig.gca().add_artist(circle1)
    ax.set_title(title_str)
    fig.savefig('{}/{}-{}.png'.format(work_dir,fn,training_mode_string),dpi=dpi)
    fig.savefig('{}/{}-{}-thumb.png'.format(work_dir,fn,training_mode_string),dpi=dpi/4)
    plt.close('all')


batch_location_supply = dlDepth * [None]
solar_disk_mask= dlDepth * [None]

def nch(d):
    return min(2**d, 4)

for d in range(dlDepth):
    n=1024/(2**d)
    location_mask_x = np.float32(np.array(n*[n*[0]]))
    location_mask_y = np.float32(np.array(n*[n*[0]]))
    mask =  np.float32(np.array(n*[n*[0]]))
    ox = n/2-0.5
    oy = n/2-0.5
    r0 = n*450.0/1024.0

    for iy in range(n):
        for ix in range(n):
            x = (ix - ox) / r0
            y = (iy - oy) / r0
            r = M.sqrt(x**2 + y**2)
            if r < 1:
                location_mask_x[iy][ix]=M.asin(x/(M.cos(M.asin(y))))
                location_mask_y[iy][ix]=M.asin(y)
                mask[iy][ix]=1
            else:
                location_mask_x[iy][ix]=-4
                location_mask_y[iy][ix]=0
                mask[iy][ix]=0
    batch_location_supply[d] = np.array(dl_batch_size * [[location_mask_x, location_mask_y]])
    batch_location_supply[d] *= global_normalization * 10.0
    solar_disk_mask[d] = np.array(dl_batch_size * [nch(d)*[mask]]) 
    if gpu_flag:
        batch_location_supply[d]=cuda.to_gpu(batch_location_supply[d])
        solar_disk_mask[d]=cuda.to_gpu(solar_disk_mask[d])

def zoom_x2(batch):
    shape = batch.data.shape
    channel_shape = shape[0:-2]
    height, width = shape[-2:]
 
    volume = reduce(operator.mul,shape,1)
 
    b1 = F.reshape(batch,(volume,1))
    b2 = F.concat([b1,b1],1)
 
    b3 = F.reshape(b2,(volume/width,2*width))
    b4 = F.concat([b3,b3],1)
 
    return F.reshape(b4, channel_shape + (2*height ,) + (2*width ,))



global sun_data
sun_data = []


modelDict = dict()
for d in range(dlDepth):
#     modelDict['convA{}'.format(d)] = F.Convolution2D( 2**d, 2**(d+1),3,stride=1,pad=1)
#     modelDict['convB{}'.format(d)] = F.Convolution2D( 2**(d+1), 2**(d+1),3,stride=1,pad=1)
#     modelDict['convV{}'.format(d)] = F.Convolution2D( 2**(d+1)+2, 2**d,3,stride=1,pad=1)
    modelDict['convA{}'.format(d)] = F.Convolution2D( nch(d), nch(d+1),3,stride=1,pad=1)
    modelDict['convB{}'.format(d)] = F.Convolution2D( nch(d+1), nch(d+1),3,stride=1,pad=1)
    modelDict['convV{}'.format(d)] = F.Convolution2D( nch(d+1)+2, nch(d),3,stride=1,pad=1)

model=chainer.FunctionSet(**modelDict)

if gpu_flag:
    model.to_gpu()

def forward_dumb(x_data,train=True,level=1):
    x = Variable(x_data)
    y = Variable(x_data)
    for d in range(level):    
        x = F.average_pooling_2d(x,2)
    for d in range(level):    
        x = zoom_x2(x)

    ret = (global_normalization**(-2))*F.mean_squared_error(F.tanh(y),F.tanh(x))
    if(not train):
        plot_img(x.data, 'd{}'.format(level), 
                 'Lv {} dumb encoder, msqe={}'.format(level, ret.data))
    return ret

        

def forward(x_data,train=True,level=1):
    global dlDepth,           training_mode_string 
    do_dropout = train
    if training_mode_string == 'p' :
       do_dropout=False 
    x = Variable(x_data, volatile = not train)
    y = Variable(x_data, volatile = not train) * Variable(solar_disk_mask[0], volatile= not train)
    if(not train and level==1):
        plot_img(y.data, 0, 'original magnetic field image')

    h = F.dropout(x, ratio = 0.1, train=do_dropout)
    for d in range(level):
        if d == level -1 :
            y = h * solar_disk_mask[d]

        h = F.tanh(getattr(model,'convA{}'.format(d))(h))
        if d < level - 1:
            h = F.dropout(h, ratio = 0.1, train=do_dropout)
        h = F.average_pooling_2d(h,2)


    for d in reversed(range(level)):    
        h = F.dropout(h, ratio = 0.1, train=do_dropout)
        h = F.tanh(getattr(model,'convB{}'.format(d))(h))    
        h = zoom_x2(h)
        sup = Variable(batch_location_supply[d], volatile = not train)
        h = F.concat([h,sup],1)
        h = F.dropout(h, ratio = 0.1, train=do_dropout)
        h = F.tanh(getattr(model,'convV{}'.format(d))(h))
        if d == level -1 :
            y_pred = h * solar_disk_mask[d]




    ret = (global_normalization**(-2))*F.mean_squared_error(F.tanh(y),F.tanh(y_pred))
    if(not train):
        plot_img(h.data, level, 'Lv {} autoencoder, msqe={}'.format(level, ret.data))
    return ret


def reference(x_data,y_data):
    global global_normalization
    x = Variable(x_data)
    y = Variable(y_data)
    print "rmsqerr_adj: {}".format((global_normalization**(-2))*F.mean_squared_error(x,y).data)



def fetch_data():
    global sun_data, global_normalization

    system('rm work/*')
    while not os.path.exists('work/0000.npz'):
        y=random.randrange(2011,2016)
        m=random.randrange(1,13)
        d=random.randrange(1,32)
        cmd='aws s3 sync --quiet s3://sdo/hmi/mag720x1024/{:04}/{:02}/{:02}/ work/'.format(y,m,d)
        system(cmd)


    p=subprocess.Popen('find work/',shell=True, stdout=subprocess.PIPE)
    stdout, _ = p.communicate()
    sun_data = []

    for fn in stdout.split('\n'):
        if not re.search('\.npz$',fn) : continue
        try:
            sun_data.append( global_normalization*np.load(fn)['img'])
        except:
            continue

# if len(sun_data)==0:
#     # where no data is available, add a dummy data for debugging
#     for i in range(10):
#         x=32*[0.333*i*i]
#         xy=32*[x]
#         sun_data.append(xy)


optimizer = dict()
for level in range(1,dlDepth+1):
    optimizer[level] = optimizers.Adam() #(alpha=3e-4)
    d=level-1
    model_of_level=dict()
    k='convA{}'.format(d)
    model_of_level[k]=modelDict[k]
    k='convB{}'.format(d)
    model_of_level[k]=modelDict[k]
    k='convV{}'.format(d)
    model_of_level[k]=modelDict[k]
    optimizer[level].setup(chainer.FunctionSet(**model_of_level).collect_parameters())

global_optimizer = optimizers.Adam()
global_optimizer.setup(model.collect_parameters())



epoch=0
while True:
    fetch_data()
    try:
        reference(np.array(sun_data[0]), np.array(sun_data[1]))
    except:
        continue

    for t in range(20): # use the same dataset 
      epoch+=1

      batch= []
    
    
      for i in range(dl_batch_size):
          start = random.randrange(len(sun_data))
          batch.append([sun_data[start]])
    
      batch=np.array(batch)
      if gpu_flag :
            batch = cuda.to_gpu(batch)

      current_depth = min(dlDepth+1,max(2,2+epoch/epoch_per_level))
      eplm = epoch % epoch_per_level 
      if eplm < epoch_per_level/3:
          training_mode_string = 'i'
          if epoch > (dlDepth+2)*epoch_per_level:
              training_mode_string = 'p'
      elif eplm < 2*epoch_per_level/3:
          training_mode_string = 'f'
      else:
          training_mode_string = 'p'

      training_mode_string = 'i'

      starting_depth = 1 if training_mode_string == 'i' else current_depth-1
      for level in range(starting_depth,current_depth):
        if level < current_depth-1:
            optimizer[level].alpha=1e-4/current_depth
        if training_mode_string == 'i':
            optimizer[level].zero_grads()
            loss = forward(batch, train=True,level=level)
            loss.backward()
            optimizer[level].update()
        else :
            global_optimizer.zero_grads()
            loss = forward(batch, train=True,level=level)
            loss.backward()
            global_optimizer.update()


        print '  '*(level-1),epoch,loss.data
    
        with(open(log_train_fn,'a')) as fp:
            fp.write('{} {} {}\n'.format(level,epoch,loss.data))
    
        if epoch == 1:
            with open("graph{}.dot".format(level), "w") as o:
                o.write(c.build_computational_graph((loss, )).dump())
            with open("graph{}.wo_split.dot".format(level), "w") as o:
                g = c.build_computational_graph((loss, ),
                                                    remove_split=True)
                o.write(g.dump())
            print('graph generated')
    
        if epoch % 20 == 1:
            loss = forward_dumb(batch, train=False,level=level)
            loss_dumb = loss.data
            loss = forward(batch,train=False,level=level)
            loss_auto = loss.data
            print "T",'  '*(level-1),epoch,loss_auto, loss_auto/loss_dumb
            with(open(log_test_fn,'a')) as fp:
                fp.write('{} {} {} {}\n'.format(level, epoch,loss_auto, loss_dumb))
