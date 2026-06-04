class AnalysisRuntimeUnavailableError(RuntimeError):
    def __init__(self, component: str, detail: str) -> None:
        self.component = component
        self.detail = detail
        super().__init__(f"{component} runtime unavailable: {detail}")
