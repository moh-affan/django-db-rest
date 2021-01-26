from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from .mixins import ListModelMixin, ListSoftDeleteModelMixin, CreateModelMixin, DestroyModelMixin, UpdateModelMixin
from django.db import models


class MyGenericViewSet(GenericViewSet):
    def get_model_class(self):
        assert self.model_class is not None and issubclass(self.model_class, models.Model), (
                "'%s' should either include a `model_class` attribute and model_class should be "
                "derived from `models.Model` class, "
                "or override the `get_model_class()` method."
                % self.__class__.__name__
        )

        return self.model_class

    def is_soft_delete(self):
        return self.soft_delete if hasattr(self, 'soft_delete') else False

    def has_detail_model(self):
        has_detail = self.detail_model_class is not None and issubclass(self.detail_model_class, models.Model)
        return has_detail, self.detail_model_class

    def get_fkey_detail(self):
        return self.fkey_detail if hasattr(self, 'fkey_detail') else None

    pass


class ModelViewSet(CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   UpdateModelMixin,
                   DestroyModelMixin,
                   ListModelMixin,
                   MyGenericViewSet):
    """
    A viewset that provides default `create()`, `retrieve()`, `update()`,
    `partial_update()`, `destroy()` and `list()` actions.
    """
    pass


class ModelSoftDeleteViewSet(mixins.CreateModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.UpdateModelMixin,
                             mixins.DestroyModelMixin,
                             ListSoftDeleteModelMixin,
                             GenericViewSet):
    """
    A viewset that provides default `create()`, `retrieve()`, `update()`,
    `partial_update()`, `destroy()` and `list()` actions.
    """
    pass
