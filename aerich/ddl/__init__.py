from enum import Enum
from typing import List, Type

from tortoise import BaseDBAsyncClient, ManyToManyFieldInstance, Model
from tortoise.backends.base.schema_generator import BaseSchemaGenerator
from tortoise.fields import CASCADE


class BaseDDL:
    schema_generator_cls: Type[BaseSchemaGenerator] = BaseSchemaGenerator
    DIALECT = "sql"
    _DROP_TABLE_TEMPLATE = 'DROP TABLE IF EXISTS "{table_name}"'
    _ADD_COLUMN_TEMPLATE = 'ALTER TABLE "{table_name}" ADD {column}'
    _DROP_COLUMN_TEMPLATE = 'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"'
    _ALTER_DEFAULT_TEMPLATE = 'ALTER TABLE "{table_name}" ALTER COLUMN "{column}" {default}'
    _RENAME_COLUMN_TEMPLATE = (
        'ALTER TABLE "{table_name}" RENAME COLUMN "{old_column_name}" TO "{new_column_name}"'
    )
    _ADD_INDEX_TEMPLATE = (
        'ALTER TABLE "{table_name}" ADD {unique}INDEX "{index_name}" ({column_names})'
    )
    _DROP_INDEX_TEMPLATE = 'ALTER TABLE "{table_name}" DROP INDEX "{index_name}"'
    _ADD_FK_TEMPLATE = 'ALTER TABLE "{table_name}" ADD CONSTRAINT "{fk_name}" FOREIGN KEY ("{db_column}") REFERENCES "{table}" ("{field}") ON DELETE {on_delete}'
    _DROP_FK_TEMPLATE = 'ALTER TABLE "{table_name}" DROP FOREIGN KEY "{fk_name}"'
    _M2M_TABLE_TEMPLATE = 'CREATE TABLE "{table_name}" ("{backward_key}" {backward_type} NOT NULL REFERENCES "{backward_table}" ("{backward_field}") ON DELETE CASCADE,"{forward_key}" {forward_type} NOT NULL REFERENCES "{forward_table}" ("{forward_field}") ON DELETE {on_delete}){extra}{comment};'
    _MODIFY_COLUMN_TEMPLATE = 'ALTER TABLE "{table_name}" MODIFY COLUMN {column}'
    _CHANGE_COLUMN_TEMPLATE = (
        'ALTER TABLE "{table_name}" CHANGE {old_column_name} {new_column_name} {new_column_type}'
    )

    def __init__(self, client: "BaseDBAsyncClient"):
        self.client = client
        self.schema_generator = self.schema_generator_cls(client)

    def create_table(self, model: "Type[Model]"):
        return self.schema_generator._get_table_sql(model, True)["table_creation_string"]

    def drop_table(self, model: "Type[Model]"):
        return self._DROP_TABLE_TEMPLATE.format(table_name=model._meta.db_table)

    def create_m2m_table(self, model: "Type[Model]", field: ManyToManyFieldInstance):
        return self._M2M_TABLE_TEMPLATE.format(
            table_name=field.through,
            backward_table=model._meta.db_table,
            forward_table=field.related_model._meta.db_table,
            backward_field=model._meta.db_pk_column,
            forward_field=field.related_model._meta.db_pk_column,
            backward_key=field.backward_key,
            backward_type=model._meta.pk.get_for_dialect(self.DIALECT, "SQL_TYPE"),
            forward_key=field.forward_key,
            forward_type=field.related_model._meta.pk.get_for_dialect(self.DIALECT, "SQL_TYPE"),
            on_delete=CASCADE,
            extra=self.schema_generator._table_generate_extra(table=field.through),
            comment=self.schema_generator._table_comment_generator(
                table=field.through, comment=field.description
            )
            if field.description
            else "",
        )

    def drop_m2m(self, field: ManyToManyFieldInstance):
        return self._DROP_TABLE_TEMPLATE.format(table_name=field.through)

    def _get_default(self, model: "Type[Model]", field_describe: dict):
        db_table = model._meta.db_table
        default = field_describe.get("default")
        if isinstance(default, Enum):
            default = default.value
        db_column = field_describe.get("db_column")
        auto_now_add = field_describe.get("auto_now_add", False)
        auto_now = field_describe.get("auto_now", False)
        if default is not None or auto_now_add:
            if field_describe.get("field_type") in ["UUIDField", "TextField", "JSONField"]:
                default = ""
            else:
                try:
                    default = self.schema_generator._column_default_generator(
                        db_table,
                        db_column,
                        self.schema_generator._escape_default_value(default),
                        auto_now_add,
                        auto_now,
                    )
                except NotImplementedError:
                    default = ""
        else:
            default = None
        return default

    def add_column(self, model: "Type[Model]", field_describe: dict, is_pk: bool = False):
        db_table = model._meta.db_table
        description = field_describe.get("description")
        db_column = field_describe.get("db_column")
        db_field_types = field_describe.get("db_field_types")
        default = self._get_default(model, field_describe)
        if default is None:
            default = ""
        return self._ADD_COLUMN_TEMPLATE.format(
            table_name=db_table,
            column=self.schema_generator._create_string(
                db_column=db_column,
                field_type=db_field_types.get(self.DIALECT, db_field_types.get("")),
                nullable="NOT NULL" if not field_describe.get("nullable") else "",
                unique="UNIQUE" if field_describe.get("unique") else "",
                comment=self.schema_generator._column_comment_generator(
                    table=db_table,
                    column=db_column,
                    comment=field_describe.get("description"),
                )
                if description
                else "",
                is_primary_key=is_pk,
                default=default,
            ),
        )

    def drop_column(self, model: "Type[Model]", column_name: str):
        return self._DROP_COLUMN_TEMPLATE.format(
            table_name=model._meta.db_table, column_name=column_name
        )

    def modify_column(self, model: "Type[Model]", field_describe: dict, is_pk: bool = False):
        db_table = model._meta.db_table
        db_field_types = field_describe.get("db_field_types")
        default = self._get_default(model, field_describe)
        if default is None:
            default = ""
        return self._MODIFY_COLUMN_TEMPLATE.format(
            table_name=db_table,
            column=self.schema_generator._create_string(
                db_column=field_describe.get("db_column"),
                field_type=db_field_types.get(self.DIALECT) or db_field_types.get(""),
                nullable="NOT NULL" if not field_describe.get("nullable") else "",
                unique="",
                comment=self.schema_generator._column_comment_generator(
                    table=db_table,
                    column=field_describe.get("db_column"),
                    comment=field_describe.get("description"),
                )
                if field_describe.get("description")
                else "",
                is_primary_key=is_pk,
                default=default,
            ),
        )

    def rename_column(self, model: "Type[Model]", old_column_name: str, new_column_name: str):
        return self._RENAME_COLUMN_TEMPLATE.format(
            table_name=model._meta.db_table,
            old_column_name=old_column_name,
            new_column_name=new_column_name,
        )

    def change_column(
        self, model: "Type[Model]", old_column_name: str, new_column_name: str, new_column_type: str
    ):
        return self._CHANGE_COLUMN_TEMPLATE.format(
            table_name=model._meta.db_table,
            old_column_name=old_column_name,
            new_column_name=new_column_name,
            new_column_type=new_column_type,
        )

    def add_index(self, model: "Type[Model]", field_names: List[str], unique=False):
        return self._ADD_INDEX_TEMPLATE.format(
            unique="UNIQUE " if unique else "",
            index_name=self.schema_generator._generate_index_name(
                "idx" if not unique else "uid", model, field_names
            ),
            table_name=model._meta.db_table,
            column_names=", ".join([self.schema_generator.quote(f) for f in field_names]),
        )

    def drop_index(self, model: "Type[Model]", field_names: List[str], unique=False):
        return self._DROP_INDEX_TEMPLATE.format(
            index_name=self.schema_generator._generate_index_name(
                "idx" if not unique else "uid", model, field_names
            ),
            table_name=model._meta.db_table,
        )

    def add_fk(self, model: "Type[Model]", field_describe: dict, reference_table_describe: dict):
        db_table = model._meta.db_table

        db_column = field_describe.get("raw_field")
        reference_id = reference_table_describe.get("pk_field").get("db_column")
        fk_name = self.schema_generator._generate_fk_name(
            from_table=db_table,
            from_field=db_column,
            to_table=reference_table_describe.get("table"),
            to_field=reference_table_describe.get("pk_field").get("db_column"),
        )
        return self._ADD_FK_TEMPLATE.format(
            table_name=db_table,
            fk_name=fk_name,
            db_column=db_column,
            table=field_describe.get("name"),
            field=reference_id,
            on_delete=field_describe.get("on_delete"),
        )

    def drop_fk(self, model: "Type[Model]", field_describe: dict, reference_table_describe: dict):
        db_table = model._meta.db_table
        return self._DROP_FK_TEMPLATE.format(
            table_name=db_table,
            fk_name=self.schema_generator._generate_fk_name(
                from_table=db_table,
                from_field=field_describe.get("raw_field"),
                to_table=reference_table_describe.get("table"),
                to_field=reference_table_describe.get("pk_field").get("db_column"),
            ),
        )

    def alter_column_default(self, model: "Type[Model]", field_describe: dict):
        db_table = model._meta.db_table
        default = self._get_default(model, field_describe)
        return self._ALTER_DEFAULT_TEMPLATE.format(
            table_name=db_table,
            column=field_describe.get("db_column"),
            default="SET" + default if default is not None else "DROP DEFAULT",
        )

    def alter_column_null(self, model: "Type[Model]", field_describe: dict):
        raise NotImplementedError

    def set_comment(self, model: "Type[Model]", field_describe: dict):
        raise NotImplementedError
