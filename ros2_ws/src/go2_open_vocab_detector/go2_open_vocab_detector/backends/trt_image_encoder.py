import tensorrt as trt
import torch

class _TrtImageEncoder:
    def __init__(self, engine_path: str, device: str):
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as f:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        self.ctx = self.engine.create_execution_context()

    def infer(self, x: torch.Tensor) -> torch.Tensor:
        x = x.contiguous()
        self.ctx.set_input_shape("images", tuple(x.shape))
        out = torch.empty((x.shape[0], 512), dtype=torch.float16, device=x.device)
        self.ctx.execute_async_v2(
            [x.data_ptr(), out.data_ptr()],
            torch.cuda.current_stream().cuda_stream,
        )
        return out