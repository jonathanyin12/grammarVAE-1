import copy
from keras import backend as K
from keras.losses import binary_crossentropy
from keras.models import Model
from keras.layers import Input, Dense, Lambda, Reshape
from keras.layers.core import Dense, Activation, Flatten, RepeatVector
from keras.layers.wrappers import TimeDistributed
from keras.layers.recurrent import GRU
from keras.layers.convolutional import Convolution1D
import tensorflow as tf
import zinc_grammar as G

masks_K = K.variable(G.masks)
ind_of_ind_K = K.variable(G.ind_of_ind)

MAX_LEN_FINGERPRINT = 1024
MAX_LEN = 150
DIM = G.D

class MoleculeVAE():

    autoencoder = None
    
    def create(self,
               charset,
               max_length = MAX_LEN,
               max_length_fpt=MAX_LEN_FINGERPRINT,
               latent_rep_size = 2,
               weights_file = None):
        charset_length = len(charset)
        
        x = Input(shape=(max_length, charset_length))
        _, z = self._buildEncoder(x, latent_rep_size, max_length, max_length_fpt)
        self.encoder = Model(x, z)

        encoded_input = Input(shape=(latent_rep_size,))
        self.decoder = Model(
            encoded_input,
            self._buildDecoder(
                encoded_input,
                latent_rep_size,
                max_length_fpt
             )
        )

        x1 = Input(shape=(max_length, charset_length))
        vae_loss, z1 = self._buildEncoder(x1, latent_rep_size, max_length, max_length_fpt)
        self.autoencoder = Model(
            x1,
            self._buildDecoder(
                z1,
                latent_rep_size,
                max_length_fpt
            )
        )

        # for obtaining mean and log variance of encoding distribution
        x2 = Input(shape=(max_length, charset_length))
        (z_m, z_l_v) = self._encoderMeanVar(x2, latent_rep_size, max_length, max_length_fpt)
        self.encoderMV = Model(inputs=x2, outputs=[z_m, z_l_v])

        if weights_file:
            self.autoencoder.load_weights(weights_file)
            self.encoder.load_weights(weights_file, by_name = True)
            self.decoder.load_weights(weights_file, by_name = True)
            self.encoderMV.load_weights(weights_file, by_name = True)

        self.autoencoder.compile(optimizer = 'Adam',
                                 loss = vae_loss,
                                 metrics = ['accuracy'])


    def _encoderMeanVar(self, x, latent_rep_size, max_length, max_length_fpt, epsilon_std = 0.01):
        h = Convolution1D(9, 9, activation = 'relu', name='conv_1')(x)
        h = Convolution1D(9, 9, activation = 'relu', name='conv_2')(h)
        h = Convolution1D(10, 11, activation = 'relu', name='conv_3')(h)
        h = Flatten(name='flatten_1')(h)
        h = Dense(435, activation = 'relu', name='dense_1')(h)

        z_mean = Dense(latent_rep_size, name='z_mean', activation = 'linear')(h)
        z_log_var = Dense(latent_rep_size, name='z_log_var', activation = 'linear')(h)

        return (z_mean, z_log_var) 


    def _buildEncoder(self, x, latent_rep_size, max_length, max_length_fpt, epsilon_std = 0.01):
        h = Convolution1D(9, 9, activation = 'relu', name='conv_1')(x)
        h = Convolution1D(9, 9, activation = 'relu', name='conv_2')(h)
        h = Convolution1D(10, 11, activation = 'relu', name='conv_3')(h)
        h = Flatten(name='flatten_1')(h)
        h = Dense(435, activation = 'relu', name='dense_1')(h)

        def sampling(args):
            z_mean_, z_log_var_ = args
            batch_size = K.shape(z_mean_)[0]
            epsilon = K.random_normal(shape=(batch_size, latent_rep_size), mean=0., stddev = epsilon_std)
            return z_mean_ + K.exp(z_log_var_ / 2) * epsilon

        z_mean = Dense(latent_rep_size, name='z_mean', activation = 'linear')(h)
        z_log_var = Dense(latent_rep_size, name='z_log_var', activation = 'linear')(h)

        # this function is the main change.
        # essentially we mask the training data so that we are only allowed to apply
        #   future rules based on the current non-terminal
        def conditional(x_true, x_pred, max_l, charset_l):
            most_likely = K.argmax(x_true)
            most_likely = tf.reshape(most_likely,[-1]) # flatten most_likely
            ix2 = tf.expand_dims(tf.gather(ind_of_ind_K, most_likely),1) # index ind_of_ind with res
            ix2 = tf.cast(ix2, tf.int32) # cast indices as ints 
            M2 = tf.gather_nd(masks_K, ix2) # get slices of masks_K with indices
            M3 = tf.reshape(M2, [-1,max_l,charset_l]) # reshape them
            P2 = tf.multiply(K.exp(x_pred),M3) # apply them to the exp-predictions
            P2 = tf.divide(P2,K.sum(P2,axis=-1,keepdims=True)) # normalize predictions
            return P2

        def vae_loss(x, x_decoded_mean):
            print('vae_loss', K.int_shape(true))
            print('vae_loss_2', K.int_shape(pred_decoded_mean))
#             x_decoded_mean = conditional(x, x_decoded_mean, max_length_fpt, 1) # we add this new function to the loss
#             x = K.flatten(x)
#             x_decoded_mean = K.flatten(x_decoded_mean)
            xent_loss = max_length_fpt * binary_crossentropy(x, x_decoded_mean)
            kl_loss = - 0.5 * K.mean(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis = -1)
            return xent_loss + kl_loss

        return (vae_loss, Lambda(sampling, output_shape=(latent_rep_size,), name='lambda')([z_mean, z_log_var]))

    def _buildDecoder(self, z, latent_rep_size, max_length_fpt):
        h = Dense(latent_rep_size, name='latent_input', activation = 'relu')(z)
        h = Dense(512, name='dense_2', activation = 'relu')(h)
        h = Dense(max_length_fpt, name='dense_3', activation = 'sigmoid')(h)
        h = Reshape((max_length_fpt, 1), name='decoded_mean')(h)
  
        return h # don't do softmax, we do this in the loss now

    def save(self, filename):
        self.autoencoder.save_weights(filename)
    
    def load(self, charset, weights_file, latent_rep_size = 2, max_length=MAX_LEN, max_length_fpt=MAX_LEN_FINGERPRINT):
        self.create(charset, max_length = max_length, max_length_fpt=max_length_fpt, weights_file = weights_file, latent_rep_size = latent_rep_size)
