#coding:utf-8
import math
import numpy as np 
import tensorflow as tf
from config import cfg
import tensorflow.contrib.slim as slim

def ins_norm(input, reuse=True, name="in"):
    """Instance Normalization
    
    args:
        input: input tensor;
        reuse (tf.bool): whether to reuse parameter
        name (string): name of this op
    return:
        instance normalized result 
    """
    with tf.variable_scope(name, reuse=reuse):
        eps = 1e-5
        mean, sigma = tf.nn.moments(input, [1, 2], keep_dims=True)
        normalized = (input - mean) / (tf.sqrt(sigma) + eps)
    return normalized
    
def pixel_norm(x, train=True, name="pn"):
    '''Pixel channel-wise normalization
    
    Pixe channel-wise normalization from "PROGRESSIVE GROWING OF GANS FOR
    IMPROVED QUALITY, STABILITY, AND VARIATION"
    '''
    with tf.variable_scope(name):
        norm_axis = len(x.get_shape()) - 1
        return x * tf.rsqrt(tf.reduce_mean(tf.square(x), axis=norm_axis, keep_dims=True) + 1e-8)

def bn(x, train=True, name="bn", epsilon=1e-5, momentum = 0.9):
    """Batch Normalization implemented by tensorflow
    
    args:
        x: input tensor
        train (bool): BN mode, "train" or "test"
    return:
        Batch Normalization result
    """
    return tf.contrib.layers.batch_norm(x,
                    decay=momentum, 
                    updates_collections=None,
                    epsilon=epsilon,
                    scale=True,
                    is_training=train,
                    scope=name)
                           
class batch_norm(object):
    def __init__(self, epsilon=1e-5, momentum = 0.9, name="batch_norm"):
        with tf.variable_scope(name):
           self.epsilon  = epsilon
           self.momentum = momentum
           self.name = name
    def __call__(self, x, is_train=True):
        return tf.contrib.layers.batch_norm(x,
                        decay=self.momentum, 
                        updates_collections=None,
                        epsilon=self.epsilon,
                        scale=True,
                        is_training=is_train,
                        scope=self.name)

class batch_norm_mosv(object):
    """Batch normalization with mean, offset, scale and variance
    
    This class is for load pretrained model from binary file (e.g. caffe model).
    Read parameters of mean, offset, scale and variance.
    
    """
    def __init__(self, mosv_dict, name="batch_norm"):
        with tf.variable_scope(name):
            self.name = name
            self.mean  = mosv_dict['mean']
            self.offset = mosv_dict['offset']
            self.scale = mosv_dict['scale']
            self.variance = mosv_dict['variance']
            self.epsilon = 1e-5
    def __call__(self, x):
        return tf.nn.batch_normalization(x, 
                                         mean=self.mean, 
                                         variance=self.variance, 
                                         offset=self.offset, 
                                         scale=self.scale, 
                                         variance_epsilon=self.epsilon, 
                                         name=self.name)
                          
def local(x,filters,name,kernel_size=3,strides=[1,1],padding='valid'):
    """Local layer
    """
    with tf.variable_scope(name):
        return tf.contrib.keras.layers.LocallyConnected2D(
                 filters=filters,
                 kernel_size=kernel_size,
                 strides=strides,
                 padding=padding,
                 kernel_initializer=tf.truncated_normal_initializer(stddev=cfg.stddev))(x)
            
def conv2d(inputs, filters, name, kernel_size = 3, strides = 1, padding='same', bias=cfg.use_bias,
           dilation_rate = 1, trainable = True, activation = None, reuse = False):
    return tf.layers.conv2d(inputs, filters = filters,
             kernel_size = kernel_size,
             padding = padding,
             strides = strides,
             dilation_rate = dilation_rate,
             activation = activation,
             trainable = trainable,
             reuse = reuse,
             use_bias = bias,
             kernel_initializer = tf.truncated_normal_initializer(stddev=cfg.stddev),
             kernel_regularizer = tf.contrib.layers.l2_regularizer(0.0001),
             name = name)

def deconv2d(inputs, filters, name, kernel_size = 3, strides = 1, padding='same',
           trainable = True, activation = None, reuse = False, bias=cfg.use_bias):
    return tf.layers.conv2d_transpose(inputs, filters = filters,
             kernel_size = kernel_size,
             padding = padding,
             strides = strides,
             activation = activation,
             trainable = trainable,
             reuse = reuse,
             use_bias = bias,
             kernel_initializer = tf.truncated_normal_initializer(stddev=cfg.stddev),
             kernel_regularizer = tf.contrib.layers.l2_regularizer(0.0001),
             name = name)

def deconv2d_w(input_, output_shape,
             k_h=5, k_w=5, d_h=2, d_w=2, stddev=0.02,
             name="deconv2d", with_w=False):
    with tf.variable_scope(name):
        # filter : [height, width, output_channels, in_channels]
        w = tf.get_variable('w', [k_h, k_w, output_shape[-1], input_.get_shape()[-1]],
                            initializer=tf.random_normal_initializer(stddev=stddev))
        
        try:
            deconv = tf.nn.conv2d_transpose(input_, w, output_shape=output_shape,
                                strides=[1, d_h, d_w, 1])

        # Support for verisons of TensorFlow before 0.7.0
        except AttributeError:
            deconv = tf.nn.deconv2d(input_, w, output_shape=output_shape,
                                strides=[1, d_h, d_w, 1])

        biases = tf.get_variable('biases', [output_shape[-1]], initializer=tf.constant_initializer(0.0))
        deconv = tf.reshape(tf.nn.bias_add(deconv, biases), deconv.get_shape())

        if with_w:
            return deconv, w, biases
        else:
            return deconv

def fullyConnect(inputs, units, name, bias=cfg.use_bias, trainable = True, activation = None, reuse = False):
    return tf.layers.dense(inputs, units = units,
             kernel_initializer = tf.truncated_normal_initializer(stddev=cfg.stddev),
             kernel_regularizer = tf.contrib.layers.l2_regularizer(0.0001),
             activation = activation,
             trainable = trainable,
             use_bias = bias,
             reuse = reuse,
             name = name)
             
def lrelu(x, leak=0.2, name="lrelu"):
    return tf.maximum(x, leak*x)

def res_block(inputs, name, is_train, normal='bn',kernel_size = 3, strides = 1, padding='same', bias=cfg.use_bias):
    """Residual block with batch normalization
    """
    with tf.variable_scope(name):
        norm = bn if(normal=='bn') else pixel_norm 
        filters = inputs.get_shape().as_list()[-1]
        conv1 = tf.nn.relu(norm(conv2d(inputs, filters, 'conv1', 
                                kernel_size=kernel_size, strides = strides),is_train,'norm1'))
        conv2 = norm(conv2d(conv1, filters, 'conv2', 
                                kernel_size=kernel_size, strides = strides),is_train,'norm2')
        return tf.nn.relu(tf.add(inputs, conv2))

def res_block_ln(inputs, name, kernel_size = 3, strides = 1, padding='same', bias=cfg.use_bias):
    """Residual block with layer normalization
    """
    with tf.variable_scope(name):
        filters = inputs.get_shape().as_list()[-1]
        conv1 = tf.nn.relu(slim.layer_norm(conv2d(inputs, filters, 'conv1', 
                                kernel_size=kernel_size, strides = strides)))
        conv2 = slim.layer_norm(conv2d(conv1, filters, 'conv2', 
                                kernel_size=kernel_size, strides = strides))     
        return tf.nn.relu(tf.add(inputs, conv2))
