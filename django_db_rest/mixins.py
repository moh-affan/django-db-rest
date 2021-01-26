from datetime import datetime, date
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import models
from django.db import transaction, DatabaseError, IntegrityError
from django.db.models.fields import DateField, DecimalField
# from django.db.models import
from django.db.models.fields.related import ForeignKey
from django.utils import timezone
from psycopg2 import errors
from rest_framework import status
from rest_framework.response import Response
from rest_framework.settings import api_settings

from .exception import MyException


class PrepareDataMixin:
    def prepare_data(self, request, data, model_class, return_obj=False, is_update=False):
        # model_class = self.get_model_class()
        if is_update:
            try:
                modificator = model_class._meta.get_field('modificator')
            except FieldDoesNotExist:
                modificator = None
            if modificator is not None:
                data['modificator'] = request.user
                data['updated_at'] = timezone.now()
        else:
            try:
                creator = model_class._meta.get_field('creator')
            except FieldDoesNotExist:
                creator = None
            if creator is not None:
                data['creator'] = request.user

        field_names = [f.attname if hasattr(f, 'attname') else '' for f in model_class._meta.get_fields()]
        field_names = field_names + [f.name for f in model_class._meta.get_fields()]
        field_names = set(field_names)
        data_keys = [d for d in data.keys()]
        for key in data_keys:
            if key not in field_names:
                data.pop(key)
        for flds in model_class._meta.get_fields():
            if isinstance(flds, ForeignKey) and not any([x in flds.name for x in ["creator", "modificator"]]):
                related_model = flds.related_model
                if flds.attname in data:
                    att = data.pop(flds.attname)
                    if isinstance(att, models.Model):
                        data[flds.name] = att
                    else:
                        rf = related_model.objects.filter(id=att).first()
                        data[flds.name] = rf
            if isinstance(flds, DateField) and not any([x in flds.name for x in ["created_at", "updated_at"]]):
                if flds.name in data:
                    dt = data.pop(flds.name)
                    if isinstance(dt, date):
                        data[flds.name] = dt
                    else:
                        if dt is not None:
                            if len(str(dt).split('-')[0]) == 4:
                                data[flds.name] = datetime.strptime(dt, "%Y-%m-%d").date()
                            else:
                                data[flds.name] = datetime.strptime(dt, "%d-%m-%Y").date()
            if isinstance(flds, DecimalField):
                if flds.name in data:
                    dt = data.pop(flds.name)
                    data[flds.name] = Decimal(str(dt).replace(',', '.'))
        if return_obj:
            obj = model_class.objects.create(**data)
            return obj
        else:
            return data


class CreateModelMixin(PrepareDataMixin):

    def create(self, request, *args, **kwargs):
        model_class = self.get_model_class()
        try:
            with transaction.atomic():
                detail = None
                if 'detail' in request.data:
                    detail = request.data.pop('detail')
                # print(detail)
                obj = self.prepare_data(request, request.data, model_class, True)
                # obj.save()
                if detail is not None and isinstance(detail, list):
                    for d in detail:
                        # print(d)
                        is_detail, detail_model_class = self.has_detail_model()
                        fkey_name = self.get_fkey_detail()
                        if is_detail and fkey_name is not None:
                            d[fkey_name] = obj
                            handle_detail_create = getattr(self, "handle_detail_create", None)
                            if callable(handle_detail_create):
                                handle_detail_create(request, d, detail_model_class)
                            else:
                                detail = self.prepare_data(request, d, detail_model_class, True)
                                detail.save()
                serializer_class = self.get_serializer_class()
                serializer = serializer_class(obj)
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except DatabaseError as e:
            print(e)
            return Response({'message': 'Data gagal disimpan, pastikan data yang Anda masukkan benar'},
                            status=status.HTTP_406_NOT_ACCEPTABLE)
        except MyException as e:
            return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)

    def perform_create(self, obj):
        try:
            obj.save()
        except MyException as e:
            return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)
        except IntegrityError as e:
            print(e)
            print(e.args)
            if 'unique constraint' in e.args or 'duplicate key' in e.args:
                return Response({'message': "Item telah ada"}, status=status.HTTP_409_CONFLICT)
            else:
                return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)
        except errors.UniqueViolation as e:
            return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)

    def get_success_headers(self, data):
        try:
            return {'Location': str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}


class UpdateModelMixin(PrepareDataMixin):
    """
    Update a model instance.
    """

    def perform_update(self, data, model_class):
        data_id = data.pop('id')
        try:
            model_class.objects.filter(id=data_id).update(**data)
        except MyException as e:
            return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(model_class.objects.get(id=data_id))
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    def update(self, request, *args, **kwargs):
        model_class = self.get_model_class()
        try:
            with transaction.atomic():
                detail = None
                if 'detail' in request.data:
                    detail = request.data.pop('detail')
                data = self.prepare_data(request, request.data, model_class, is_update=True)
                data_id = data.pop('id')
                obj = model_class.objects.get(id=data_id)
                model_class.objects.filter(id=data_id).update(**data)
                detail_ids = []
                fkey_name = self.get_fkey_detail()
                if detail is not None and isinstance(detail, list):
                    for d in detail:
                        is_detail, detail_model_class = self.has_detail_model()
                        if is_detail and fkey_name is not None:
                            detail = self.prepare_data(request, d, detail_model_class, return_obj=False, is_update=True)
                            if 'id' in detail:
                                # update berdasarkan id
                                detail_id = detail.pop('id')
                                detail_ids.append(detail_id)
                                detail_model_class.objects.filter(id=detail_id).update(**detail)
                            else:
                                # buat objek baru
                                d[fkey_name] = obj
                                detail_obj = self.prepare_data(request, d, detail_model_class, return_obj=True)
                                # detail_obj.save()
                                detail_ids.append(detail_obj.id)
                    delete_par = {fkey_name: obj}
                    detail_model_class.objects.filter(**delete_par).exclude(id__in=detail_ids).delete()
                serializer_class = self.get_serializer_class()

                serializer = serializer_class(model_class.objects.get(id=data_id))
                return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
        except DatabaseError as e:
            print(e)
            return Response({'message': 'Data gagal disimpan, pastikan data yang Anda masukkan benar'},
                            status=status.HTTP_406_NOT_ACCEPTABLE)
        except MyException as e:
            return Response({'message': "{}".format(e)}, status=status.HTTP_409_CONFLICT)
        # return self.perform_update(data, model_class)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


class ListModelMixin:
    """
    List a queryset.
    """

    def list(self, request, *args, **kwargs):
        _filter = request.GET.get('filter', default=False)
        limit = request.GET.get('limit', default='')
        sorter = request.GET.get('sorter', default='')
        filterer = request.GET.get('filterer', default='')
        exclude = request.GET.get('exclude', default='')
        pg = request.GET.get('page', default='')
        if _filter:
            queryset = self.filter_queryset(self.get_filtered_queryset(request=request))
        else:
            queryset = self.filter_queryset(self.get_queryset())
        if sorter != '':
            sorter = sorter.split(",")
            queryset = queryset.order_by(*sorter)
        else:
            try:
                queryset = queryset.order_by('id')
            except FieldError:
                print('no_id')
        if filterer != '':
            filter_pars = {}
            for pars in filterer.strip(",").split(","):
                kv = pars.split(":")
                if len(kv) == 3:
                    filter_pars["{}__{}".format(kv[0], kv[2])] = kv[1]
                else:
                    filter_pars["{}__icontains".format(kv[0])] = kv[1]
            queryset = queryset.filter(**filter_pars)
        if exclude != '':
            exclude_pars = {}
            for pars in exclude.strip(",").split(","):
                kv = pars.split(":")
                if len(kv) == 3:
                    exclude_pars["{}__{}".format(kv[0], kv[2])] = kv[1]
                else:
                    exclude_pars["{}__icontains".format(kv[0])] = kv[1]
            queryset = queryset.exclude(**exclude_pars)
            # print(queryset.query)
        if limit != '':
            queryset = queryset[:int(limit)]
        if pg != '':
            page = self.paginate_queryset(queryset)
            # print('page')
            # print(page.query)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ListSoftDeleteModelMixin:
    """
    List a queryset.
    """

    def list(self, request, *args, **kwargs):
        _filter = request.GET.get('filter', default=False)
        pg = request.GET.get('page', default='')
        limit = request.GET.get('limit', default='')
        sorter = request.GET.get('sorter', default='')
        filterer = request.GET.get('filterer', default='')
        exclude = request.GET.get('exclude', default='')
        # queryset = self.filter_queryset(self.get_filtered_queryset(request=request))
        if _filter:
            queryset = self.filter_queryset(self.get_filtered_queryset(request=request))
        else:
            queryset = self.filter_queryset(self.get_queryset())
        if limit != '':
            queryset = queryset[:int(limit)]
        if sorter != '':
            sorter = sorter.split(",")
            queryset = queryset.order_by(*sorter)
        if filterer != '':
            filter_pars = {}
            for pars in filterer.split(","):
                kv = pars.split(":")
                filter_pars["{}__icontains".format(kv[0])] = kv[1]
            queryset = queryset.filter(**filter_pars)
        if exclude != '':
            exclude_pars = {}
            for pars in exclude.strip(",").split(","):
                kv = pars.split(":")
                if len(kv) == 3:
                    exclude_pars["{}__{}".format(kv[0], kv[2])] = kv[1]
                else:
                    exclude_pars["{}__icontains".format(kv[0])] = kv[1]
            queryset = queryset.exclude(**exclude_pars)
        queryset = queryset.exclude(deleted_at=None)
        if pg != '':
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class DestroyModelMixin:
    """
    Destroy a model instance.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        pk = kwargs['pk']
        self.perform_destroy(instance, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance, user):
        if self.is_soft_delete():
            try:
                with transaction.atomic():
                    # model_class = self.get_model_class()
                    # obj = model_class.objects.get(id=pk)
                    instance.deleted_at = timezone.now()
                    instance.deleted_by = user
                    instance.save()
            except DatabaseError:
                return Response(status=status.HTTP_406_NOT_ACCEPTABLE)
        else:
            instance.delete()
