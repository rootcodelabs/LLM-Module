import { FC, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, FormSelect } from 'components';
import Pagination from 'components/molecules/Pagination';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { formattedArray } from 'utils/commonUtilts';
import DataModelCard from 'components/molecules/LLMConnectionCard';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';
import { ButtonAppearanceTypes } from 'enums/commonEnums';
import NoDataView from 'components/molecules/NoDataView';
import './LLMConnections.scss';
import { modelStatuses, trainingStatuses } from 'config/dataModelsConfig';
import LLMConnectionCard from 'components/molecules/LLMConnectionCard';
import { mockLLMConnections } from 'mockData/llmConnectionData';

const LLMConnections: FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [pageIndex, setPageIndex] = useState<number>(1);

  const [view, setView] = useState<'list' | 'individual'>('list');
  const isModelDataLoading = false;
  const [filters, setFilters] = useState({
    modelName: 'all',
    modelStatus: 'all',
    trainingStatus: 'all',
    deploymentEnvironment: 'all',
    sort: 'createdAt desc',
  });



  const handleFilterChange = (
    name: string,
    value: string | number | undefined | { name: string; id: string }
  ) => {
    setFilters((prevFilters) => ({
      ...prevFilters,
      [name]: value,
    }));
  };

  return (
    <div>
      <div className="container">
        {!isModelDataLoading ? (
          <div>
            <div>
              <div className="title_container">
                <div className="title">{t('dataModels.dataModels')}</div>
                <Button
                  appearance="primary"
                  size="m"
                  onClick={() => navigate('/create-data-model')}
                >
                  {t('dataModels.createModel')}
                </Button>
              </div>
              <div className="search-panel">
                <div className="models-filter-div">
                  <FormSelect
                    label=""
                    name=""
                    placeholder={t('dataModels.filters.modelStatus') ?? ''}
                    options={modelStatuses}
                    onSelectionChange={(selection) =>
                      handleFilterChange('modelStatus', selection?.value ?? '')
                    }
                    defaultValue={filters?.modelStatus}
                  />
                  <FormSelect
                    label=""
                    name=""
                    placeholder={t('dataModels.filters.maturity') ?? ''}
                    options={[]}
                    onSelectionChange={(selection) =>
                      handleFilterChange('deploymentEnvironment', selection?.value)
                    }
                    defaultValue={filters?.deploymentEnvironment}
                  />

                  <FormSelect
                    label=""
                    name=""
                    placeholder={t('dataModels.filters.sort') ?? ''}
                    options={[
                      {
                        label: t('dataModels.sortOptions.dataModelAsc'),
                        value: 'modelName asc',
                      },
                      {
                        label: t('dataModels.sortOptions.dataModelDesc'),
                        value: 'modelName desc',
                      },
                      {
                        label: t('dataModels.sortOptions.createdDateDesc'),
                        value: 'createdAt desc',
                      },
                      {
                        label: t('dataModels.sortOptions.createdDateAsc'),
                        value: 'createdAt asc',
                      },
                    ]}
                    onSelectionChange={(selection) =>
                      handleFilterChange('sort', selection?.value)
                    }
                    defaultValue={filters?.sort}
                  />

                  <div className="filter-reset-button">
                    <Button
                      onClick={() =>
                        setFilters({
                          modelName: 'all',
                          modelStatus: 'all',
                          trainingStatus: 'all',
                          deploymentEnvironment: 'all',
                          sort: 'createdAt desc',
                        })
                      }
                      appearance={ButtonAppearanceTypes.SECONDARY}
                    >
                      {t('global.reset') ?? ''}
                    </Button>
                  </div>
                </div>
              </div>
              { <div className="m-30-0">
                <p>Deployed LLM Connection</p>
                <div className="grid-container m-30-0">
                  <LLMConnectionCard
                            key={mockLLMConnections[0]?.llmConnectionId}
                            llmConnectionId={mockLLMConnections[0]?.llmConnectionId}
                            llmConnectionName={mockLLMConnections[0]?.llmConnectionName}
                            isActive={mockLLMConnections[0]?.isActive}
                            deploymentEnv={mockLLMConnections[0]?.deploymentEnv}
                            budgetStatus={mockLLMConnections[0]?.budgetStatus}
                            platform={mockLLMConnections[0]?.platform}
                            model={mockLLMConnections[0]?.model}
                          />
                  </div>
              </div>}

              {mockLLMConnections?.length > 0 ? (
                <div><p>Other Data Models</p>
                  <div className="grid-container m-30-0">

                    {mockLLMConnections?.map(
                      (llmConnection, index: number) => {
                        return (
                          <LLMConnectionCard
                            key={llmConnection?.llmConnectionId}
                            llmConnectionId={llmConnection?.llmConnectionId}
                            llmConnectionName={llmConnection?.llmConnectionName}
                            isActive={llmConnection?.isActive}
                            deploymentEnv={llmConnection?.deploymentEnv}
                            budgetStatus={llmConnection?.budgetStatus}
                            platform={llmConnection?.platform}
                            model={llmConnection?.model}
                          />
                        );
                      }
                    )}
                  </div>
                </div>

              ) : (
                <NoDataView text={t('dataModels.noModels') ?? ''} />
              )}
            </div>
            <Pagination
              pageCount={1}
              pageIndex={pageIndex}
              canPreviousPage={pageIndex > 1}
              canNextPage={pageIndex < 10}
              onPageChange={setPageIndex}
            />
          </div>
        ) : (
          <CircularSpinner />
        )}
      </div>
    </div>
  );
};

export default LLMConnections;
