
import numpy

import theano
import theano.tensor as T
from six.moves import xrange
from theano.gof import local_optimizer
from theano.sandbox.cuda.basic_ops import as_cuda_ndarray_variable
from theano.misc import strutil

from theano.tensor.nnet.ConvGrad3D import ConvGrad3D
from theano.sandbox.cuda.opt import gpu_optimizer
from theano.sandbox.cuda import (CudaNdarrayType, HostFromGpu,
                                 host_from_gpu, GpuOp)


class GpuConvGrad3D(GpuOp):
    """
    GPU version of gradient of ConvGrad3D with respect to W.

    """

    def make_node(self, V, d, WShape, dCdH):
        """

        Parameters
        ----------
        V
            Visible.
        d
            Strides.
        WShape
            Shapes of the weights -> shape of this op output.
        dCdH
            Other input with what V will be convolved.

        """
        V_ = as_cuda_ndarray_variable(V)
        d_ = T.as_tensor_variable(d)
        WShape_ = T.as_tensor_variable(WShape)
        dCdH_ = as_cuda_ndarray_variable(dCdH)
        broad = (False,)*5
        return theano.Apply(self, inputs=[V_, d_, WShape_, dCdH_],
                            outputs=[CudaNdarrayType(dtype=V_.dtype,
                                                     broadcastable=broad)()])

    def perform_(self, node, inputs, output_storage):
        V, d, WShape, dCdH = inputs
        print("GpuConvGrad3D python code (warning not updated to new format)")

        # partial C / partial W[j,z,k,l,m] = sum_i sum_p sum_q sum_r (partial C /partial H[i,j,p,q,r] ) *  V[i,z,dr*p+k,dc*q+l,dt*r+m]

        batchSize = dCdH.shape[0]
        outputFilters = dCdH.shape[1]
        outputHeight = dCdH.shape[2]
        outputWidth = dCdH.shape[3]
        outputDur = dCdH.shape[4]
        assert V.shape[0] == batchSize
        inputFilters = V.shape[1]
        inputHeight = V.shape[2]
        inputWidth = V.shape[3]
        inputDur = V.shape[4]
        dr, dc, dt = d

        dCdW = numpy.zeros(WShape, dtype=V.dtype)

        # block
        for j in range(0, WShape[0]):
            for z in range(0, WShape[1]):
                for k in range(0, WShape[2]):
                    for l in range(0, WShape[3]):
                        # threads
                        for m in range(0, WShape[4]):
                            # thread
                            for i in range(0, batchSize):
                                for p in range(0, outputHeight):
                                    for q in range(0, outputWidth):
                                        for r in range(0, outputDur):
                                            dCdW[j, z, k, l, m] += dCdH[i, j, p, q, r] * V[i, z, dr*p+k, dc*q+l, dt*r+m]

        output_storage[0][0] = dCdW

    def c_code(self, node, nodename, inputs, outputs, sub):
        V, d, WShape, dCdH = inputs
        fail = sub['fail']

        dCdW = outputs[0]

        codeSource =  """
            ///////////// < code generated by GpuConvGrad3D >

            //printf("\t\t\t\tGpuConvGrad3DW c code\\n");

            //Check dimensionality of inputs
            if (CudaNdarray_NDIM(%(dCdH)s) != 5)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: dCdH must be a 5-d CudaNdArray");
                %(fail)s
            }

            if (CudaNdarray_NDIM(%(V)s) != 5)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: V must be a 5-d CudaNdArray");
                %(fail)s
            }

            if (CudaNdarray_NDIM(%(WShape)s) != 1)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: WShape must be a 1-d CudaNdArray");
                %(fail)s
            }

            if (PyArray_NDIM(%(d)s) != 1)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: d must be a 1-d CudaNdArray");
                %(fail)s
            }

            if (PyArray_DIMS(%(d)s)[0] != 3)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: 3 stride lengths arguments expected(for row, col, and time) but %%li were given", PyArray_DIMS(%(d)s)[0]);
                %(fail)s
            }

{ // for fail

            //Read and check sizes of inputs
            const int batchSize = CudaNdarray_HOST_DIMS(%(V)s)[0];
            if (PyArray_DIMS(%(WShape)s)[0] != 5)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: WShape must specify a 5-d shape");
                %(fail)s
            }
            if (!PyArray_ISCONTIGUOUS(%(WShape)s))
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: WShape must be contiguous");
                %(fail)s

            }
{ //for fail
            dtype_%(WShape)s * WShape = (dtype_%(WShape)s *) PyArray_DATA(%(WShape)s);
            const int outputChannels =  WShape[0];
            const int inputChannels = CudaNdarray_HOST_DIMS(%(V)s)[4];
            if (WShape[4] != inputChannels)
            {
                PyErr_Format(PyExc_ValueError, "ConvGrad3D: W operates on a %%d channel image but the image has %%d channels",WShape[4],inputChannels);
                %(fail)s

            }
{ //extra scope so fail works
            const int filterHeight = WShape[1];
            const int filterWidth = WShape[2];
            const int filterDur = WShape[3];
            const int vidHeight = CudaNdarray_HOST_DIMS(%(V)s)[1];
            const int vidWidth = CudaNdarray_HOST_DIMS(%(V)s)[2];
            const int vidDur = CudaNdarray_HOST_DIMS(%(V)s)[3];
            if (vidHeight < filterHeight)
            {
                PyErr_Format(PyExc_ValueError, "W has a height of %%i but V is only %%i pixels tall", filterHeight, vidHeight);
                %(fail)s
            }
            if (vidWidth < filterWidth)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: W has a width of %%i but V is only %%i pixels wide", filterWidth, vidWidth);
                %(fail)s
            }
            if (vidDur < filterDur)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: W has a duration of %%i but V is only %%i pixels long", filterWidth, vidWidth);
                %(fail)s
            }

{ // extra scope so fail works
            //Read and check stride arguments
            const int dr = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,0);
            const int dc = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,1);
            const int dt = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,2);
            if (dr <= 0 || dc <= 0 || dt <= 0)
            {
                PyErr_Format(PyExc_ValueError, "GpuConvGrad3D: Strides must all be positive but are %%i, %%i, %%i",dr,dc,dt);
                %(fail)s
            }


            //Compute correctl sized of output
            const int outputHeight = int( (vidHeight - filterHeight) / dr )+1;
            const int outputWidth = int( (vidWidth - filterWidth) / dc )+1;
            const int outputDur = int( (vidDur - filterDur) / dt ) +1;

            if (CudaNdarray_HOST_DIMS(%(dCdH)s)[0] != batchSize ||
                CudaNdarray_HOST_DIMS(%(dCdH)s)[4] != outputChannels ||
                CudaNdarray_HOST_DIMS(%(dCdH)s)[1] != outputHeight ||
                CudaNdarray_HOST_DIMS(%(dCdH)s)[2] != outputWidth ||
                CudaNdarray_HOST_DIMS(%(dCdH)s)[3] != outputDur)
            {
                PyErr_Format(PyExc_ValueError, "dCdH is the wrong size, expected (%%i,%%i,%%i,%%i,%%i), got (%%i,%%i,%%i,%%i,%%i)", batchSize, outputHeight, outputWidth, outputDur, outputChannels, CudaNdarray_HOST_DIMS(%(dCdH)s)[0], CudaNdarray_HOST_DIMS(%(dCdH)s)[1], CudaNdarray_HOST_DIMS(%(dCdH)s)[2] ,CudaNdarray_HOST_DIMS(%(dCdH)s)[3], CudaNdarray_HOST_DIMS(%(dCdH)s)[4] );
                %(fail)s
            }
{ // extra scope for fail

            npy_intp dims[5];
            dims[0] = outputChannels;
            dims[4] = inputChannels;
            dims[1] = filterHeight;
            dims[2] = filterWidth;
            dims[3] = filterDur;

            if(!(%(dCdW)s)  || CudaNdarray_HOST_DIMS(%(dCdW)s)[0]!=dims[0] ||
                  CudaNdarray_HOST_DIMS(%(dCdW)s)[1]!=dims[1] ||
                  CudaNdarray_HOST_DIMS(%(dCdW)s)[2]!=dims[2] ||
                  CudaNdarray_HOST_DIMS(%(dCdW)s)[3]!=dims[3] ||
                  CudaNdarray_HOST_DIMS(%(dCdW)s)[4]!=dims[4] ){
               Py_XDECREF(%(dCdW)s);
               %(dCdW)s = (CudaNdarray*)CudaNdarray_NewDims(5,dims);

               if (!(%(dCdW)s)) {
                PyErr_Format(PyExc_MemoryError, "GpuConvGrad3D: Could not allocated dCdW");
                %(fail)s
               }
            }
{ //for fail
            const int dcdhs4 = CudaNdarray_HOST_STRIDES(%(dCdH)s)[4];
            const int dcdhs3 = CudaNdarray_HOST_STRIDES(%(dCdH)s)[3];
            const int dcdhs1 = CudaNdarray_HOST_STRIDES(%(dCdH)s)[1];
            const int dcdhs2 = CudaNdarray_HOST_STRIDES(%(dCdH)s)[2];
            const int dcdhs0 = CudaNdarray_HOST_STRIDES(%(dCdH)s)[0];
            const int vs4 = CudaNdarray_HOST_STRIDES(%(V)s)[4];
            const int vs3 = CudaNdarray_HOST_STRIDES(%(V)s)[3];
            const int vs2 = CudaNdarray_HOST_STRIDES(%(V)s)[2];
            const int vs1 = CudaNdarray_HOST_STRIDES(%(V)s)[1];
            const int vs0 = CudaNdarray_HOST_STRIDES(%(V)s)[0];

bool out_contiguous = CudaNdarray_is_c_contiguous(%(dCdW)s);
int version = -1;
int verbose = 0;
bool subsample =(dr>1)||(dc>1)||(dt>1);
bool work_complete = false;
if(out_contiguous && (version==0||version==-1) && WShape[4]<=512 && !work_complete){
    //conv_rows_stack
    dim3 grid(WShape[0]*WShape[4],WShape[1]*WShape[2]);//outputHeight*outputWidth);
    dim3 threads(WShape[3]);

    int shared_size=0;

        convgrad_rows_stack<<<grid, threads, shared_size>>>(
        CudaNdarray_DEV_DATA(%(V)s), CudaNdarray_DEV_DATA(%(dCdH)s), CudaNdarray_DEV_DATA(%(dCdW)s),
        vidHeight, vidWidth, vidDur,
        filterHeight, filterWidth, filterDur,
        WShape[0], WShape[1], WShape[2], WShape[3], WShape[4],
        outputHeight,outputWidth,outputDur,
        batchSize, outputChannels, inputChannels,
        dr,dc,dt,
        vs3,vs2,vs1,vs4,vs0,
        dcdhs3,dcdhs2,dcdhs1,dcdhs4,dcdhs0);

        CNDA_THREAD_SYNC;
        cudaError_t sts = cudaGetLastError();
        if (cudaSuccess == sts)
        {
            work_complete = true;
            if (verbose>1) printf("threads.x=%%i, threads.y=%%i, grid.x=%%i, grid.y=%%i, shared_size=%%i, nb_threads=%%i\\n", threads.x, threads.y, grid.x, grid.y, shared_size, threads.x * threads.y);
            if (verbose) printf("INFO: used 'conv_rows_stack' version\\n");
        }
        else
        {
            if (verbose) printf("threads.x=%%i, threads.y=%%i, grid.x=%%i, grid.y=%%i, shared_size=%%i, nb_threads=%%i\\n", threads.x, threads.y, grid.x, grid.y, shared_size, threads.x * threads.y);
            if (verbose) printf("ERROR: all implementations failed for GpuConv3D! (%%s)",cudaGetErrorString(sts));
            PyErr_Format(PyExc_RuntimeError, "ERROR: all implementations failed for GpuConvGrad3D! (%%s)",
                    cudaGetErrorString(sts));
            %(fail)s
        }

}
if(!work_complete){
            PyErr_Format(PyExc_RuntimeError, "ERROR: no implementations executed for this GpuConv3D!");
            %(fail)s
}
}}}}} // extra scope for fail
            ///////////// < /code generated by GpuConvGrad3D >
        """

        return strutil.render_string(codeSource, locals())

    def c_support_code_apply(self, node, nodename):
        # This code is not sensitive to the ignore_border flag.
        # It runs for every position in the output z, and then computes the gradient for the
        # input pixels that were downsampled to that z-position.
        codeSource =  """
__global__ void
//thread block size = WShape[4]
//grid block size = (WShape[0]*WShape[1],WShape[2]*WShape[3])
//
convgrad_rows_stack( float* img, float* dCdH, float* dCdW,
                 int img_len, int img_wid, int img_dur,
                 int dCdW_len, int dCdW_wid, int dCdW_dur,
                 int wsh0, int wsh1, int wsh2, int wsh3, int wsh4,
                 int out_len, int out_wid, int out_dur,
                 int batchSize, int nkern, int nstack,
                 int dr, int dc, int dt,
                 int img_stride_frame, int img_stride_col, int img_stride_row,
                 int img_stride_stack, int img_stride_batch,
                 int dCdW_stride_frame, int dCdW_stride_col, int dCdW_stride_row,
                 int dCdW_stride_stack, int dCdW_stride_nkern)
{
  int __shared__ kern_id, stack_id;
  float  __shared__ *d_img, *d_kern;

  kern_id= blockIdx.x%nkern;
  stack_id = blockIdx.x/nkern;

  const int dCdW_row = blockIdx.y%ws1;
  const int dCdW_col = blockIdx.y/ws1;
  const int dCdW_frame=threadIdx.x;

  img +=stack_id*img_stride_stack;
  dCdH +=kern_id*dCdW_stride_stack;
  float sum = 0.0f;

  for(int i=0;i<batchSize;i++){
      for(int p=0;p<out_len;p++){
          for(int q=0;q<out_wid;q++){
              for(int r=0;r<out_dur;r++){
                  sum += dCdH[i*dCdW_stride_nkern+p*dCdW_stride_row+q*dCdW_stride_col+r*dCdW_stride_frame] *
                         img[i*img_stride_batch+(dr*p+dCdW_row)*img_stride_row+(dc*q+dCdW_col)*img_stride_col+(dt*r+dCdW_frame)*img_stride_frame];
              }
          }
      }
  }
  dCdW[kern_id*wsh1*wsh2*wsh3*wsh4+//the good batch
      stack_id+//the output image
      dCdW_row*wsh2*wsh3*wsh4+//the output row
      dCdW_col*wsh3*wsh4 + //the output_col
      dCdW_frame*wsh4] = sum;

}
/*
        #block
        for j in xrange(0,WShape[0]):
            for z in xrange(0,WShape[1]):
                for k in xrange(0,WShape[2]):
                    for l in xrange(0,WShape[3]):
                        #threads
                        for m in xrange(0,WShape[4]):
                            #thread
                            for i in xrange(0,batchSize):
                                for p in xrange(0,outputHeight):
                                    for q in xrange(0,outputWidth):
                                        for r in xrange(0,outputDur):
                                            dCdW[j,z,k,l,m] += dCdH[i,j,p,q,r] * V[i,z,dr*p+k,dc*q+l,dt*r+m]
*/
"""
        return codeSource

gpu_conv_grad3d = GpuConvGrad3D()


@local_optimizer([ConvGrad3D])
def local_gpu_conv_grad3d(node):
    if isinstance(node.op, ConvGrad3D):
        if numpy.any([i.owner and isinstance(i.owner.op, HostFromGpu)
                      for i in node.inputs]):
            if numpy.all([o.type.dtype == 'float32' for o in node.outputs]):
                V, d, WShape, dCdH = node.inputs
                return [host_from_gpu(gpu_conv_grad3d(
                    as_cuda_ndarray_variable(V),
                    d,
                    WShape,
                    as_cuda_ndarray_variable(dCdH)))]
# Not enabled by default as we don't want people to use it.
gpu_optimizer.register("local_gpu_conv_grad3d", local_gpu_conv_grad3d)
