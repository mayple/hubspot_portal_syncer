"""
HubSpot Portal property syncer.
"""

# Copyright 2017-2021 (c) Mayple. All rights reserved.
# Copying and/or distribution of this file is prohibited.

import dataclasses
from typing import Dict
from typing import List
from typing import Optional

import requests
from hubspot import HubSpot
from hubspot.crm.properties import ModelProperty
from hubspot.crm.properties import PropertyGroup


# For more info about the HubSpot API etc: https://developers.hubspot.com/docs/api/crm/properties
# And about the Python SDK: https://github.com/HubSpot/hubspot-api-python


# =======================================================================================================================
# Public Members
# =======================================================================================================================

@dataclasses.dataclass
class Portal:
    portalId: int
    name: str
    apiKey: str
    apiClient: Optional[HubSpot] = None


class ResultMessages:

    def __init__(self, objectType: str, sourcePortal: Portal, targetPortal: Portal):
        self._messages = []

        self._objectType = objectType
        self._sourcePortal = sourcePortal
        self._targetPortal = targetPortal

    def addMessage(self, message: str) -> None:
        formattedMessage = f'{self._sourcePortal.name}->{self._targetPortal.name} ({self._objectType}): {message}'
        self._messages.append(formattedMessage)

    def getMessages(self) -> List[str]:
        return self._messages


def preparePortal(portal: Portal) -> None:
    if not portal.apiKey:
        raise ValueError(
            f'Missing API key for portal {portal.name}',
        )
    response = requests.get(
        url=f'https://api.hubapi.com/integrations/v1/me?hapikey={portal.apiKey}',
    )
    readPortalId = response.json()['portalId']
    assert readPortalId == portal.portalId

    apiClient = HubSpot(api_key=portal.apiKey)
    portal.apiClient = apiClient


def syncProperties(
    objectType: str,
    sourcePortal: Portal,
    targetPortal: Portal,
) -> ResultMessages:
    print(f"Syncing {objectType} properties and groups from source={sourcePortal.name} to target={targetPortal.name}")

    resultMessages = ResultMessages(
        objectType=objectType,
        sourcePortal=sourcePortal,
        targetPortal=targetPortal,
    )

    sourceContactPropertyGroups = sourcePortal.apiClient.crm.properties.groups_api.get_all(object_type=objectType)
    sourceContactPropertyGroupsByName: Dict[str, PropertyGroup] = {
        currentProperty.name: currentProperty
        for currentProperty in sourceContactPropertyGroups.results
    }

    sourceContactProperties = sourcePortal.apiClient.crm.properties.core_api.get_all(object_type=objectType)
    sourcePropertiesByName: Dict[str, ModelProperty] = {
        currentProperty.name: currentProperty
        for currentProperty in sourceContactProperties.results
    }

    targetContactPropertyGroups = targetPortal.apiClient.crm.properties.groups_api.get_all(object_type=objectType)
    targetContactPropertyGroupsByName: Dict[str, PropertyGroup] = {
        currentProperty.name: currentProperty
        for currentProperty in targetContactPropertyGroups.results
    }
    targetContactProperties = targetPortal.apiClient.crm.properties.core_api.get_all(object_type=objectType)
    targetPropertiesByName: Dict[str, ModelProperty] = {
        currentProperty.name: currentProperty
        for currentProperty in targetContactProperties.results
    }

    # PropertyGroups
    # --------------

    # Create missing:
    for name, propertyGroup in sourceContactPropertyGroupsByName.items():
        # Skip HS-owned
        if name.startswith("hs_"):
            print(
                f'Skipped HubSpot-owned property group {name} in source',
            )
            continue
        if not name in targetContactPropertyGroupsByName:
            createPropertyGroupBasedOnOtherPropertyGroup(
                resultMessages=resultMessages,
                targetPortal=targetPortal,
                objectType=objectType,
                otherPropertyGroup=propertyGroup,
            )
        else:
            # TODO: compare and sync
            print(
                f"Skipped source existing property group {name}: sync it manually, not yet implemented"
            )

    print("-------------")

    # Report extra

    for name, propertyGroup in targetContactPropertyGroupsByName.items():
        # Skip HS-owned
        if name.startswith("hs_"):
            print(
                f'Skipped HubSpot-owned property group {name} in target',
            )
            continue

        if not name in sourceContactPropertyGroupsByName:
            resultMessages.addMessage(
                f"property group {name} is only in target - delete it "
                f"manually or sync other way",
            )
        else:
            # TODO: compare and sync
            print(
                f"Skipped target existing property group {name}: sync it manually, not yet implemented"
            )

    print("-------------")

    # Properties
    # ----------

    # Create missing

    for name, currentProperty in sourcePropertiesByName.items():
        # Skip HS-owned
        if name.startswith("hs_"):
            print(
                f'Skipped HubSpot-owned property {name} in source',
            )
            continue

        if not name in targetPropertiesByName:
            createPropertyBasedOnOtherProperty(
                resultMessages=resultMessages,
                targetPortal=targetPortal,
                objectType=objectType,
                otherProperty=currentProperty,
            )
        else:
            # TODO: compare and sync
            print(
                f"Skipped source existing property {name}: sync it manually, not yet implemented"
            )

    print("-------------")

    # Report extra

    for name, currentProperty in targetPropertiesByName.items():
        # Skip HS-owned
        if name.startswith("hs_"):
            print(
                f'Skipped HubSpot-owned property group {name} in target',
            )
            continue
        if not name in sourcePropertiesByName:
            resultMessages.addMessage(
                f"property {name} is only in target - delete it "
                f"manually or sync other way",
            )
        else:
            # TODO: compare and sync
            print(
                f"Skipped target existing property {name}: sync it manually, not yet implemented"
            )

    print("-------------")

    return resultMessages


def createPropertyGroupBasedOnOtherPropertyGroup(
    resultMessages: ResultMessages,
    targetPortal: Portal,
    objectType: str,
    otherPropertyGroup: PropertyGroup,
) -> None:
    try:
        print(f"Creating new property group {otherPropertyGroup.name}")
        targetPortal.apiClient.crm.properties.groups_api.create(
            objectType,
            property_group_create={
                'name':         otherPropertyGroup.name,
                'label':        otherPropertyGroup.label,
                'displayOrder': otherPropertyGroup.display_order,
                'archived':     otherPropertyGroup.archived,
            },
        )
    except Exception as e:
        resultMessages.addMessage(
            f'Failed creating new property group {otherPropertyGroup.name}: {e}',
        )


def createPropertyBasedOnOtherProperty(
    resultMessages: ResultMessages,
    targetPortal: Portal,
    objectType: str,
    otherProperty: ModelProperty,
) -> None:
    if otherProperty.calculated:
        resultMessages.addMessage(
            f'Skipped property {otherProperty.name}: it is a calculated property, create it manually.',
        )
        return

    try:
        print(f"Creating new property {otherProperty.name}")
        targetPortal.apiClient.crm.properties.core_api.create(
            objectType,
            property_create={
                'name':                 otherProperty.name,
                'label':                otherProperty.label,
                'type':                 otherProperty.type,
                'fieldType':            otherProperty.field_type,
                'groupName':            otherProperty.group_name,
                'description':          otherProperty.description,
                'options':              otherProperty.options,
                'displayOrder':         otherProperty.display_order,
                'hasUniqueValue':       otherProperty.has_unique_value,
                'hidden':               otherProperty.hidden,
                'formField':            otherProperty.form_field,

                'calculated':           otherProperty.calculated,
                'externalOptions':      otherProperty.external_options,
                'hubspotDefined':       otherProperty.hubspot_defined,
                'referencedObjectType': otherProperty.referenced_object_type,
                'showCurrencySymbol':   otherProperty.show_currency_symbol,
            },
        )
    except Exception as e:
        resultMessages.addMessage(
            f'Failed creating new property  {otherProperty.name}: {e}',
        )


# =======================================================================================================================
# Private Members
# =======================================================================================================================

# =======================================================================================================================
# Main
# =======================================================================================================================

if __name__ == "__main__":

    portal1Portal = Portal(
        portalId=111111,
        name="portal1",
        apiKey="",
    )
    preparePortal(portal1Portal)

    portal2Portal = Portal(
        portalId=222222,
        name="portal2",
        apiKey="",
    )
    preparePortal(portal2Portal)

    portal3Portal = Portal(
        portalId=3333333,
        name="portal3",
        apiKey=""
    )
    preparePortal(portal3Portal)

    portal4Portal = Portal(
        portalId=444444,
        name="portal4",
        apiKey="",
    )
    preparePortal(portal4Portal)

    portalPairs = [
        (portal1Portal, portal2Portal),
        (portal2Portal, portal3Portal),
        (portal3Portal, portal4Portal),
    ]

    allMessages = []
    for currentSourcePortal, currentTargetPortal, in portalPairs:

        for currentObjectType in [
            "contact",
            "company",
            "deal",
            "ticket",
        ]:
            currentResultMessages = syncProperties(
                objectType=currentObjectType,
                sourcePortal=currentSourcePortal,
                targetPortal=currentTargetPortal,
            )
            allMessages.extend(currentResultMessages.getMessages())

    print("Requires manual attention:")
    print('\n'.join(allMessages))
