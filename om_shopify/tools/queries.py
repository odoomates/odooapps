""" The GraphQL queries and mutations of the Shopify Admin API used by Odoo. """

MONEY = 'shopMoney { amount currencyCode } presentmentMoney { amount currencyCode }'

ADDRESS = 'firstName lastName name company address1 address2 city zip provinceCode countryCodeV2 phone'

LOCATIONS = """
query OmShopifyLocations($cursor: String) {
  locations(first: 50, after: $cursor, includeInactive: true) {
    nodes { id name isActive fulfillsOnlineOrders }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PRODUCT_IDS = """
query OmShopifyProductIds($cursor: String, $query: String) {
  products(first: 100, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    nodes { id updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PRODUCT = """
query OmShopifyProduct($id: ID!, $cursor: String) {
  product(id: $id) {
    id title handle status descriptionHtml vendor productType tags updatedAt
    options { name position optionValues { name } }
    featuredMedia { preview { image { url } } }
    media(first: 20) { nodes { preview { image { url } } } }
    # om:metafields:product
    variants(first: 100, after: $cursor) {
      nodes {
        id title sku barcode price compareAtPrice position
        # om:metafields:variant
        media(first: 1) { nodes { preview { image { url } } } }
        selectedOptions { name value }
        inventoryItem { id tracked measurement { weight { unit value } } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

ORDER_IDS = """
query OmShopifyOrderIds($cursor: String, $query: String) {
  orders(first: 100, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    nodes { id name updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""

ORDER = f"""
query OmShopifyOrder($id: ID!) {{
  order(id: $id) {{
    id name createdAt processedAt updatedAt cancelledAt cancelReason test
    email phone note tags currencyCode presentmentCurrencyCode taxesIncluded sourceName
    displayFinancialStatus displayFulfillmentStatus paymentGatewayNames
    customer {{ id firstName lastName defaultEmailAddress {{ emailAddress }} defaultPhoneNumber {{ phoneNumber }} }}
    billingAddress {{ {ADDRESS} }}
    shippingAddress {{ {ADDRESS} }}
    totalPriceSet {{ {MONEY} }}
    totalTipReceivedSet {{ {MONEY} }}
    currentTotalDutiesSet {{ {MONEY} }}
    risk {{ recommendation assessments {{ riskLevel facts {{ description }} }} }}
    purchasingEntity {{ ... on PurchasingCompany {{ company {{ id }} location {{ id }} contact {{ id }} }} }}
    # om:metafields:order
    fulfillmentOrders(first: 10) {{ nodes {{ status assignedLocation {{ location {{ id }} }} }} }}
    lineItems(first: 250) {{
      nodes {{
        id name sku quantity currentQuantity isGiftCard requiresShipping
        variant {{ id }}
        product {{ id }}
        originalUnitPriceSet {{ {MONEY} }}
        discountAllocations {{ allocatedAmountSet {{ {MONEY} }} }}
        taxLines {{ title rate priceSet {{ {MONEY} }} }}
      }}
      pageInfo {{ hasNextPage }}
    }}
    shippingLines(first: 10) {{
      nodes {{
        title code source
        originalPriceSet {{ {MONEY} }}
        discountAllocations {{ allocatedAmountSet {{ {MONEY} }} }}
        taxLines {{ title rate priceSet {{ {MONEY} }} }}
      }}
    }}
    transactions(first: 50) {{ id kind status gateway amountSet {{ {MONEY} }} }}
    refunds(first: 50) {{
      id createdAt note
      totalRefundedSet {{ {MONEY} }}
      refundLineItems(first: 250) {{ nodes {{ quantity restockType lineItem {{ id }} subtotalSet {{ {MONEY} }} }} }}
      refundShippingLines(first: 10) {{ nodes {{ subtotalAmountSet {{ {MONEY} }} }} }}
      transactions(first: 20) {{ nodes {{ kind status gateway amountSet {{ {MONEY} }} }} }}
    }}
  }}
}}
"""

ORDER_SEARCH = """
query OmShopifyOrderSearch($query: String) {
  orders(first: 10, query: $query) { nodes { id name updatedAt } }
}
"""

ORDER_CANCEL = """
mutation OmShopifyOrderCancel($orderId: ID!, $reason: OrderCancelReason!, $refundMethod: OrderCancelRefundMethodInput!,
                              $restock: Boolean!, $notifyCustomer: Boolean, $staffNote: String) {
  orderCancel(orderId: $orderId, reason: $reason, refundMethod: $refundMethod, restock: $restock,
              notifyCustomer: $notifyCustomer, staffNote: $staffNote) {
    job { id done }
    orderCancelUserErrors { field message code }
  }
}
"""

SUGGESTED_REFUND = f"""
query OmShopifySuggestedRefund($id: ID!, $lines: [RefundLineItemInput!], $shipping: Money) {{
  order(id: $id) {{
    suggestedRefund(refundLineItems: $lines, shippingAmount: $shipping, suggestFullAmount: false) {{
      amountSet {{ {MONEY} }}
      suggestedTransactions {{ gateway kind amountSet {{ {MONEY} }} parentTransaction {{ id }} }}
    }}
  }}
}}
"""

REFUND_CREATE = """
mutation OmShopifyRefundCreate($input: RefundInput!, $key: String!) {
  refundCreate(input: $input) @idempotent(key: $key) {
    refund { id totalRefundedSet { shopMoney { amount } } }
    userErrors { field message }
  }
}
"""

FULFILLMENT_ORDERS = """
query OmShopifyFulfillmentOrders($id: ID!) {
  order(id: $id) {
    id
    fulfillmentOrders(first: 20) {
      nodes {
        id status
        assignedLocation { location { id } }
        lineItems(first: 250) { nodes { id remainingQuantity lineItem { id } } }
      }
    }
  }
}
"""

FULFILLMENT_CREATE = """
mutation OmShopifyFulfillmentCreate($fulfillment: FulfillmentInput!) {
  fulfillmentCreate(fulfillment: $fulfillment) {
    fulfillment { id status }
    userErrors { field message }
  }
}
"""

INVENTORY_SET = """
mutation OmShopifyInventorySet($input: InventorySetQuantitiesInput!, $key: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $key) {
    inventoryAdjustmentGroup { id }
    userErrors { field message code }
  }
}
"""

PRODUCT_SET = """
mutation OmShopifyProductSet($input: ProductSetInput!, $identifier: ProductSetIdentifiers) {
  productSet(input: $input, identifier: $identifier, synchronous: true) {
    product {
      id handle status
      variants(first: 250) { nodes { id sku selectedOptions { name value } inventoryItem { id tracked } } }
    }
    userErrors { field message code }
  }
}
"""

STAGED_UPLOADS = """
mutation OmShopifyStagedUploads($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}
"""

PUBLICATIONS = """
query OmShopifyPublications($cursor: String) {
  publications(first: 50, after: $cursor) { nodes { id name } pageInfo { hasNextPage endCursor } }
}
"""

PUBLISH = """
mutation OmShopifyPublish($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}
"""

VARIANTS_BULK_UPDATE = """
mutation OmShopifyVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id price }
    userErrors { field message }
  }
}
"""

VARIANT = """
query OmShopifyVariant($id: ID!) {
  productVariant(id: $id) {
    id title sku barcode
    product { id title handle status }
    inventoryItem { id tracked }
  }
}
"""

INVENTORY_LEVELS = """
query OmShopifyInventoryLevels($id: ID!, $cursor: String) {
  location(id: $id) {
    inventoryLevels(first: 250, after: $cursor) {
      nodes { item { id } quantities(names: ["available"]) { name quantity } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

CUSTOMER_IDS = """
query OmShopifyCustomerIds($cursor: String, $query: String) {
  customers(first: 100, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    nodes { id updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""

CUSTOMER = f"""
query OmShopifyCustomer($id: ID!) {{
  customer(id: $id) {{
    id firstName lastName note tags
    defaultEmailAddress {{ emailAddress }}
    defaultPhoneNumber {{ phoneNumber }}
    defaultAddress {{ {ADDRESS} }}
    # om:metafields:customer
  }}
}}
"""

PAYOUTS = """
query OmShopifyPayouts($cursor: String, $query: String) {
  shopifyPaymentsAccount {
    payouts(first: 50, after: $cursor, query: $query) {
      nodes { id issuedAt status net { amount currencyCode } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

BALANCE_TRANSACTIONS = """
query OmShopifyBalanceTransactions($cursor: String, $query: String) {
  shopifyPaymentsAccount {
    balanceTransactions(first: 100, after: $cursor, query: $query) {
      nodes {
        id type test transactionDate
        amount { amount currencyCode } fee { amount } net { amount }
        associatedOrder { id name }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

BULK_PRODUCTS = """
{
  products {
    edges {
      node {
        id title handle status descriptionHtml vendor productType tags updatedAt
        options { name position optionValues { name } }
        featuredMedia { preview { image { url } } }
        # om:metafields:product
        variants {
          edges {
            node {
              id title sku barcode price compareAtPrice position
              # om:metafields:variant
              selectedOptions { name value }
              inventoryItem { id tracked measurement { weight { unit value } } }
            }
          }
        }
      }
    }
  }
}
"""

BULK_RUN = """
mutation OmShopifyBulkRun($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation { id status }
    userErrors { field message }
  }
}
"""

BULK_STATUS = """
query OmShopifyBulkStatus($id: ID!) {
  bulkOperation(id: $id) { id status errorCode objectCount url partialDataUrl }
}
"""

COMPANY_ADDRESS = 'address1 address2 city zip zoneCode countryCode phone companyName recipient'

COMPANY_IDS = """
query OmShopifyCompanyIds($cursor: String) {
  companies(first: 100, after: $cursor) { nodes { id updatedAt } pageInfo { hasNextPage endCursor } }
}
"""

COMPANY = f"""
query OmShopifyCompany($id: ID!) {{
  company(id: $id) {{
    id name externalId note
    locations(first: 50) {{
      nodes {{
        id name externalId
        billingAddress {{ {COMPANY_ADDRESS} }}
        shippingAddress {{ {COMPANY_ADDRESS} }}
        taxSettings {{ taxExempt }}
        buyerExperienceConfiguration {{ paymentTermsTemplate {{ name dueInDays paymentTermsType }} }}
      }}
    }}
    contacts(first: 50) {{ nodes {{ id customer {{ id }} }} }}
  }}
}}
"""

PRICE_LISTS = """
query OmShopifyPriceLists($cursor: String) {
  priceLists(first: 50, after: $cursor) { nodes { id name currency } pageInfo { hasNextPage endCursor } }
}
"""

PRICE_LIST_FIXED_PRICES_ADD = """
mutation OmShopifyPriceListPrices($priceListId: ID!, $prices: [PriceListPriceInput!]!) {
  priceListFixedPricesAdd(priceListId: $priceListId, prices: $prices) {
    prices { variant { id } }
    userErrors { field code message }
  }
}
"""
