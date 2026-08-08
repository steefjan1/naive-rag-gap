targetScope = 'subscription'

@minLength(1)
@maxLength(24)
@description('Name of the azd environment. Used to derive resource names.')
param environmentName string

// No default value here on purpose. A subscription-scope deployment needs its
// own location, which azd supplies from AZURE_LOCATION - and azd only prompts
// for that when the parameter is genuinely unsatisfied. Give it a default and
// azd skips the prompt, leaves AZURE_LOCATION unset, and the deployment fails
// validation with "The 'location' property must be specified".
@description('Region for all resources. Must support Azure AI Search semantic ranker and your chosen models.')
@allowed([
  'swedencentral'
  'eastus'
  'eastus2'
  'westus3'
  'northeurope'
  'westeurope'
])
param location string

@description('Object ID of the developer who will run the samples. Defaults to the signed-in azd user.')
param principalId string = ''

@description('Search service SKU. Semantic ranker and managed identity need basic or higher.')
@allowed([
  'basic'
  'standard'
])
param searchSku string = 'basic'

param embeddingModel string = 'text-embedding-3-large'
param embeddingModelVersion string = '1'
param chatModel string = 'gpt-5-mini'

var abbrev = uniqueString(subscription().id, environmentName)
var tags = { 'azd-env-name': environmentName, project: 'naive-rag-gap' }

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    abbrev: abbrev
    principalId: principalId
    searchSku: searchSku
    embeddingModel: embeddingModel
    embeddingModelVersion: embeddingModelVersion
    chatModel: chatModel
  }
}

// These output names match the variables in .env.example, so
// `azd env get-values` produces a usable .env directly.
output AZURE_SEARCH_ENDPOINT string = resources.outputs.searchEndpoint
output AZURE_OPENAI_ENDPOINT string = resources.outputs.openAiEndpoint
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingModel
output AZURE_OPENAI_EMBEDDING_MODEL string = embeddingModel
output AZURE_OPENAI_CHAT_DEPLOYMENT string = chatModel
output AZURE_OPENAI_API_VERSION string = '2025-04-01-preview'
output AZURE_SEARCH_INDEX string = 'policies-demo'
output AZURE_SEARCH_ACL_INDEX string = 'policies-acl-demo'
output AZURE_SEARCH_KNOWLEDGE_BASE string = 'policies-kb'
output AZURE_RESOURCE_GROUP string = rg.name
